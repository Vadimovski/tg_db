"""
Модуль для работы с базой данных SQLite.
Хранит информацию о чатах и каналах Telegram.
"""
import sqlite3
import os
from typing import List, Dict, Tuple

# Получаем корневую директорию проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Путь к базе данных (относительно корня проекта)
DB_DIR = os.path.join(BASE_DIR, 'data')
DB_NAME = 'oleg_chats.db'
DB_PATH = os.path.join(DB_DIR, DB_NAME)


def ensure_data_dir():
    """Создает папку data, если она не существует."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)


def init_database():
    """
    Инициализирует базу данных и создает необходимые таблицы, если они не существуют.
    
    Таблицы:
    - chats: id, tg_id, title, participants_count, type
    - categories: id, name (UNIQUE)
    - chat_categories: chat_tg_id, category_id (связка many-to-many)
    """
    ensure_data_dir()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица чатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            title TEXT NOT NULL,
            participants_count INTEGER,
            type TEXT
        )
    ''')

    # Миграции: добавляем недостающие столбцы в существующую таблицу
    cursor.execute("PRAGMA table_info(chats)")
    columns_info = cursor.fetchall()
    column_names = {col[1] for col in columns_info}
    # Столбец type
    if "type" not in column_names:
        try:
            cursor.execute('ALTER TABLE chats ADD COLUMN type TEXT')
        except sqlite3.OperationalError:
            # Если по какой-то причине добавить столбец не удалось, продолжаем без падения
            pass
    # Столбец количества участников
    if "participants_count" not in column_names:
        try:
            cursor.execute('ALTER TABLE chats ADD COLUMN participants_count INTEGER')
        except sqlite3.OperationalError:
            # Если по какой-то причине добавить столбец не удалось, продолжаем без падения
            pass
    
    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Таблица связки чат-категория (many-to-many)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_categories (
            chat_tg_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (chat_tg_id, category_id),
            FOREIGN KEY (chat_tg_id) REFERENCES chats(tg_id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    ''')
    
    # Удаляем старый столбец category из chats, если он существует (миграция)
    try:
        cursor.execute('ALTER TABLE chats DROP COLUMN category')
    except sqlite3.OperationalError:
        # Столбец не существует, игнорируем ошибку
        pass
    
    conn.commit()
    conn.close()


def save_chats(chats: List[Dict[str, any]]):
    """
    Сохраняет или обновляет список чатов в базе данных.
    
    Args:
        chats: Список словарей с ключами 'tg_id' и 'title'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Удаляем все существующие записи перед добавлением новых
    cursor.execute('DELETE FROM chats')
    
    # Вставляем новые данные
    for chat in chats:
        chat_type = chat.get('type')
        participants_count = chat.get('participants_count')
        cursor.execute('''
            INSERT INTO chats (tg_id, title, participants_count, type)
            VALUES (?, ?, ?, ?)
        ''', (chat['tg_id'], chat['title'], participants_count, chat_type))
    
    conn.commit()
    conn.close()


def get_all_chats() -> List[Tuple[int, int, str, int, str]]:
    """
    Получает все чаты из базы данных, отсортированные по возрастанию tg_id.
    
    Returns:
        Список кортежей (id, tg_id, title, participants_count, type)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, tg_id, title, participants_count, type
        FROM chats
        ORDER BY tg_id ASC
    ''')
    
    chats = cursor.fetchall()
    conn.close()
    
    return chats


def get_chats_for_display() -> List[Tuple[int, str, int, str, str]]:
    """
    Получает чаты для отображения в таблице UI.
    Возвращает tg_id, название, количество участников, строку категорий через запятую и тип чата.
    
    Returns:
        Список кортежей (tg_id, title, participants_count, categories_string, type)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            c.tg_id, 
            c.title,
            COALESCE(c.participants_count, 0) as participants_count,
            COALESCE(GROUP_CONCAT(cat.name, ', '), '') as categories,
            c.type
        FROM chats c
        LEFT JOIN chat_categories cc ON c.tg_id = cc.chat_tg_id
        LEFT JOIN categories cat ON cc.category_id = cat.id
        GROUP BY c.tg_id, c.title, participants_count, c.type
        ORDER BY c.tg_id ASC
    ''')
    
    chats = cursor.fetchall()
    conn.close()
    
    return chats


# ========== Функции для работы с категориями ==========

def create_category(name: str) -> int:
    """
    Создает новую категорию в базе данных.
    
    Args:
        name: Название категории
        
    Returns:
        ID созданной категории
        
    Raises:
        sqlite3.IntegrityError: Если категория с таким именем уже существует
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO categories (name)
        VALUES (?)
    ''', (name,))
    
    category_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return category_id


def get_all_categories() -> List[Tuple[int, str]]:
    """
    Получает все категории из базы данных.
    
    Returns:
        Список кортежей (id, name)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name
        FROM categories
        ORDER BY name ASC
    ''')
    
    categories = cursor.fetchall()
    conn.close()
    
    return categories


def search_categories(search_term: str) -> List[Tuple[int, str]]:
    """
    Ищет категории по названию (case-insensitive поиск).
    
    Args:
        search_term: Строка для поиска
        
    Returns:
        Список кортежей (id, name)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name
        FROM categories
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY name ASC
    ''', (f'%{search_term}%',))
    
    categories = cursor.fetchall()
    conn.close()
    
    return categories


# ========== Функции для работы со связками чат-категория ==========

def get_chat_categories(chat_tg_id: int) -> List[int]:
    """
    Получает список ID категорий, присвоенных чату.
    
    Args:
        chat_tg_id: ID чата по Telegram
        
    Returns:
        Список ID категорий
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT category_id
        FROM chat_categories
        WHERE chat_tg_id = ?
    ''', (chat_tg_id,))
    
    category_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return category_ids


def add_category_to_chat(chat_tg_id: int, category_id: int) -> bool:
    """
    Добавляет категорию к чату.
    
    Args:
        chat_tg_id: ID чата по Telegram
        category_id: ID категории
        
    Returns:
        True если успешно добавлено, False если связка уже существует
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO chat_categories (chat_tg_id, category_id)
            VALUES (?, ?)
        ''', (chat_tg_id, category_id))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Связка уже существует
        conn.close()
        return False


def remove_category_from_chat(chat_tg_id: int, category_id: int):
    """
    Удаляет категорию из чата.
    
    Args:
        chat_tg_id: ID чата по Telegram
        category_id: ID категории
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM chat_categories
        WHERE chat_tg_id = ? AND category_id = ?
    ''', (chat_tg_id, category_id))
    
    conn.commit()
    conn.close()


def get_available_categories_for_chat(chat_tg_id: int) -> List[Tuple[int, str]]:
    """
    Получает список категорий, которые еще не присвоены данному чату.
    
    Args:
        chat_tg_id: ID чата по Telegram
        
    Returns:
        Список кортежей (id, name) доступных категорий
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name
        FROM categories c
        WHERE c.id NOT IN (
            SELECT cc.category_id
            FROM chat_categories cc
            WHERE cc.chat_tg_id = ?
        )
        ORDER BY c.name ASC
    ''', (chat_tg_id,))
    
    categories = cursor.fetchall()
    conn.close()
    
    return categories


def search_available_categories_for_chat(chat_tg_id: int, search_term: str) -> List[Tuple[int, str]]:
    """
    Ищет доступные категории для чата по названию (исключая уже присвоенные).
    
    Args:
        chat_tg_id: ID чата по Telegram
        search_term: Строка для поиска
        
    Returns:
        Список кортежей (id, name)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.name
        FROM categories c
        WHERE c.id NOT IN (
            SELECT cc.category_id
            FROM chat_categories cc
            WHERE cc.chat_tg_id = ?
        )
        AND LOWER(c.name) LIKE LOWER(?)
        ORDER BY c.name ASC
    ''', (chat_tg_id, f'%{search_term}%'))
    
    categories = cursor.fetchall()
    conn.close()
    
    return categories

