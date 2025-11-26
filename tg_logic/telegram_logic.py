"""
Модуль для работы с Telegram API через библиотеку Telethon.
Обеспечивает аутентификацию и получение списка чатов/каналов.
"""
import os
import json
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.errors import SessionPasswordNeededError
from typing import List, Dict, Optional, Tuple

# Получаем корневую директорию проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Путь к файлу конфигурации (относительно корня проекта)
CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'config.json')

# Путь к файлу сессии (относительно корня проекта)
SESSION_DIR = os.path.join(BASE_DIR, 'data')
SESSION_NAME = 'session'
SESSION_PATH = os.path.join(SESSION_DIR, SESSION_NAME)


def ensure_session_dir():
    """Создает папку для хранения сессии, если она не существует."""
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)


def save_api_credentials(api_id: str, api_hash: str):
    """
    Сохраняет API credentials в JSON файл.
    
    Args:
        api_id: ID приложения Telegram
        api_hash: Hash приложения Telegram
    """
    ensure_session_dir()
    
    config = {
        'api_id': api_id,
        'api_hash': api_hash
    }
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def load_api_credentials() -> Optional[Tuple[str, str]]:
    """
    Загружает API credentials из JSON файла.
    
    Returns:
        Кортеж (api_id, api_hash) или None, если файл не найден
    """
    # Сначала проверяем переменные окружения
    api_id = os.getenv('TELEGRAM_API_ID', '')
    api_hash = os.getenv('TELEGRAM_API_HASH', '')
    
    if api_id and api_hash:
        return (api_id, api_hash)
    
    # Затем проверяем файл конфигурации
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_id = config.get('api_id', '')
                api_hash = config.get('api_hash', '')
                
                if api_id and api_hash:
                    return (api_id, api_hash)
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f'Ошибка при чтении конфигурации: {e}')
    
    return None


def get_api_credentials() -> Tuple[str, str]:
    """
    Получает API credentials из различных источников.
    Приоритет: переменные окружения > файл config.json
    
    Returns:
        Кортеж (api_id, api_hash)
        
    Raises:
        ValueError: если credentials не найдены
    """
    credentials = load_api_credentials()
    
    if credentials:
        return credentials
    
    raise ValueError(
        "API_ID и API_HASH не найдены. "
        "Используйте кнопку 'Подключиться' для ввода данных или "
        "установите переменные окружения TELEGRAM_API_ID и TELEGRAM_API_HASH."
    )


class TelegramManager:
    """Класс для управления подключением к Telegram и получения данных."""
    
    def __init__(self, api_id: str = None, api_hash: str = None):
        """
        Инициализирует TelegramManager.
        
        Args:
            api_id: ID приложения Telegram (можно получить на https://my.telegram.org/auth)
            api_hash: Hash приложения Telegram
        """
        # Если не переданы напрямую, пытаемся загрузить из конфига
        if not api_id or not api_hash:
            try:
                loaded_credentials = get_api_credentials()
                api_id = api_id or loaded_credentials[0]
                api_hash = api_hash or loaded_credentials[1]
            except ValueError:
                pass  # Пропускаем, если не найдены - проверим ниже
        
        if not api_id or not api_hash:
            raise ValueError(
                "API_ID и API_HASH должны быть указаны. "
                "Получите их на https://my.telegram.org/auth и используйте "
                "кнопку 'Подключиться' для ввода данных."
            )
        
        # Преобразуем api_id в строку для TelegramClient
        try:
            self.api_id = int(api_id)
        except (ValueError, TypeError):
            raise ValueError("API_ID должен быть числом")
        
        self.api_hash = str(api_hash)
        
        ensure_session_dir()
        # Создаем event loop один раз для всех операций
        self.loop = asyncio.new_event_loop()
        # Создаем клиент с этим event loop
        self.client = TelegramClient(SESSION_PATH, self.api_id, self.api_hash, loop=self.loop)

    def get_current_user_name(self) -> Optional[str]:
        """
        Возвращает отображаемое имя текущего аккаунта Telegram.
        Пытается вернуть сначала полное имя, затем username, затем телефон.
        """
        try:
            asyncio.set_event_loop(self.loop)

            async def _get_me():
                return await self.client.get_me()

            me = self.loop.run_until_complete(_get_me())
            if not me:
                return None

            # Собираем человеко-понятное имя
            parts = []
            if getattr(me, "first_name", None):
                parts.append(me.first_name)
            if getattr(me, "last_name", None):
                parts.append(me.last_name)
            full_name = " ".join(parts).strip()

            if full_name:
                return full_name

            username = getattr(me, "username", None)
            if username:
                return f"@{username}"

            phone = getattr(me, "phone", None)
            if phone:
                return f"+{phone}" if not phone.startswith("+") else phone

            return None
        except Exception:
            return None
    
    def connect(self, phone: str = None, code: str = None, password: str = None) -> Tuple[bool, str]:
        """
        Подключается к Telegram и аутентифицирует пользователя.
        
        Args:
            phone: Номер телефона (если требуется авторизация)
            code: Код подтверждения (если требуется авторизация)
            password: Пароль 2FA (если требуется)
        
        Returns:
            Кортеж (успех: bool, сообщение: str)
            Сообщение может быть запросом на ввод данных (например, "phone" или "code" или "password")
        """
        try:
            # Устанавливаем event loop в текущий поток
            asyncio.set_event_loop(self.loop)
            
            # Подключаемся (если еще не подключены)
            if not self.client.is_connected():
                self.loop.run_until_complete(self.client.connect())
            
            # Проверяем, авторизован ли пользователь
            is_authorized = self.loop.run_until_complete(self.client.is_user_authorized())
            
            if not is_authorized:
                # Пользователь не авторизован
                if not phone:
                    # Первый шаг - требуется номер телефона
                    return (False, "phone")
                
                # У нас есть номер телефона
                if not code:
                    # Второй шаг - требуется код подтверждения
                    # Отправляем запрос на код (если еще не отправлен)
                    try:
                        self.loop.run_until_complete(self.client.send_code_request(phone))
                        return (False, "code")  # Требуется код
                    except Exception as e:
                        error_str = str(e)
                        # Если код уже отправлен, это нормально - просто просим ввести код
                        if "phone code" in error_str.lower() or "already" in error_str.lower():
                            return (False, "code")
                        return (False, f"Ошибка при отправке кода: {error_str}")
                
                # У нас есть номер телефона и код
                # Пытаемся войти с кодом
                try:
                    self.loop.run_until_complete(self.client.sign_in(phone, code))
                    return (True, "Подключено успешно")
                except SessionPasswordNeededError:
                    # Требуется пароль 2FA
                    if not password:
                        return (False, "password")  # Требуется пароль 2FA
                    try:
                        self.loop.run_until_complete(self.client.sign_in(password=password))
                        return (True, "Подключено успешно")
                    except Exception as e:
                        return (False, f"Ошибка при вводе пароля: {str(e)}")
                except Exception as e:
                    error_str = str(e)
                    # Если код неправильный или истек
                    if "code" in error_str.lower():
                        return (False, f"Неверный код. Попробуйте снова. Ошибка: {error_str}")
                    return (False, f"Ошибка при вводе кода: {error_str}")
            
            # Пользователь уже авторизован
            return (True, "Уже подключено")
        except Exception as e:
            error_msg = f'Ошибка при подключении к Telegram: {str(e)}'
            print(error_msg)
            return (False, error_msg)
    
    def get_chats_and_channels(self) -> List[Dict[str, any]]:
        """
        Получает список всех чатов и каналов (исключая личные чаты).
        
        Returns:
            Список словарей с ключами:
            - 'tg_id'             : ID сущности в Telegram
            - 'title'             : отображаемое название
            - 'type'              : 'channel' для каналов (broadcast),
                                     'chat' для групп и супергрупп
            - 'participants_count': количество участников (если доступно, иначе None)
        """
        from telethon.tl.types import User
        
        chats_list = []
        
        try:
            # Устанавливаем event loop в текущий поток
            asyncio.set_event_loop(self.loop)
            
            # Итерируемся по всем диалогам синхронно
            async def get_dialogs():
                dialogs = []
                async for dialog in self.client.iter_dialogs():
                    dialogs.append(dialog)
                return dialogs
            
            dialogs = self.loop.run_until_complete(get_dialogs())
            
            for dialog in dialogs:
                entity = dialog.entity
                
                # Пропускаем личные чаты (User)
                if isinstance(entity, User):
                    continue
                
                # Включаем только каналы и группы
                if isinstance(entity, (Channel, Chat)):
                    # Получаем название чата
                    title = dialog.name
                    if not title:
                        title = getattr(entity, 'title', 'Без названия')
                    
                    # Определяем тип сущности для отображения в таблице:
                    # - broadcast Channel      -> "channel"
                    # - megagroup Channel/Chat -> "chat"
                    if isinstance(entity, Channel):
                        # Канал-рассылка (one-way) -> "channel"
                        if getattr(entity, "broadcast", False):
                            chat_type = "channel"
                        # Супергруппа (megagroup) -> "chat"
                        elif getattr(entity, "megagroup", False):
                            chat_type = "chat"
                        else:
                            # На всякий случай считаем прочие Channel как "channel"
                            chat_type = "channel"
                    elif isinstance(entity, Chat):
                        # Обычная группа -> "chat"
                        chat_type = "chat"

                    # Пытаемся взять количество участников, если эта информация уже есть в сущности
                    participants_count = getattr(entity, "participants_count", None)

                    chats_list.append({
                        'tg_id': entity.id,
                        'title': title,
                        'type': chat_type,
                        'participants_count': participants_count
                    })
        
        except Exception as e:
            print(f'Ошибка при получении списка чатов: {e}')
        
        return chats_list
    
    def disconnect(self):
        """Отключается от Telegram."""
        try:
            if self.loop and not self.loop.is_closed():
                asyncio.set_event_loop(self.loop)
                is_connected = self.loop.run_until_complete(self.client.is_connected())
                if is_connected:
                    self.loop.run_until_complete(self.client.disconnect())
        except Exception:
            pass  # Игнорируем ошибки при отключении


def authenticate_and_get_chats(api_id: str = None, api_hash: str = None) -> List[Dict[str, any]]:
    """
    Упрощенная функция для аутентификации и получения списка чатов.
    
    Args:
        api_id: ID приложения Telegram
        api_hash: Hash приложения Telegram
        
    Returns:
        Список словарей с информацией о чатах
    """
    manager = TelegramManager(api_id, api_hash)
    
    try:
        if manager.connect():
            chats = manager.get_chats_and_channels()
            return chats
        else:
            return []
    finally:
        manager.disconnect()

