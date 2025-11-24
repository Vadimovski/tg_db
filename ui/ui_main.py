"""
Главный файл приложения.
Создает GUI на основе customtkinter для отображения чатов Telegram.
"""
import customtkinter as ctk
from tkinter import ttk, messagebox
import threading
import os
import sys
import sqlite3
import json

# Добавляем корневую директорию проекта в путь
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from tg_logic import TelegramManager, save_api_credentials, load_api_credentials
from db_logic import (
    init_database, save_chats, get_chats_for_display,
    create_category, get_available_categories_for_chat, search_available_categories_for_chat,
    add_category_to_chat
)


# Настройка темы customtkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TelegramChatsApp(ctk.CTk):
    """Главное окно приложения для отображения чатов Telegram."""
    
    def __init__(self):
        super().__init__()
        
        # Настройка окна
        self.title("Telegram Chats Manager")
        self.geometry("900x600")
        
        # Инициализация базы данных
        init_database()
        
        # Переменные для хранения данных Telegram
        self.api_id = None
        self.api_hash = None
        self.telegram_manager = None
        self.current_phone = None  # Номер телефона для авторизации
        
        # Загружаем сохраненные credentials при запуске
        self.load_saved_credentials()
        
        # Загружаем настройки столбцов из config
        self.column_config = self.load_column_config()
        
        # Загружаем настройки таблицы из config
        self.table_settings = self.load_table_settings()
        
        # Создание UI
        self.create_widgets()
        
        # Проверяем статус подключения при запуске
        if self.api_id and self.api_hash:
            # Проверяем авторизацию в фоновом потоке
            self.check_connection_status()
        
        # Загрузка данных при запуске, если они есть в БД
        self.refresh_table()
    
    def load_saved_credentials(self):
        """Загружает сохраненные API credentials из файла или переменных окружения."""
        credentials = load_api_credentials()
        if credentials:
            self.api_id, self.api_hash = credentials
    
    def load_column_config(self):
        """
        Загружает настройки столбцов из config.json.
        Возвращает словарь с настройками или значения по умолчанию.
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')
        
        # Значения по умолчанию
        default_config = {
            "ID чата по ТГ": {
                "heading": "ID чата по Telegram",
                "width": 300,
                "anchor": "center"
            },
            "Название": {
                "heading": "Название",
                "width": 200,
                "anchor": "w"
            },
            "Категории": {
                "heading": "Категории",
                "width": 200,
                "anchor": "w"
            },
            "Действия": {
                "heading": "+",
                "width": 50,
                "anchor": "center"
            }
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    column_config = config.get('table_columns', {})
                    
                    # Объединяем с настройками по умолчанию (приоритет у config файла)
                    result = default_config.copy()
                    result.update(column_config)
                    return result
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f'Ошибка при чтении настроек столбцов: {e}')
                return default_config
        
        return default_config
    
    def load_table_settings(self):
        """
        Загружает настройки таблицы (шрифт, высота строк) из config.json.
        Возвращает словарь с настройками или значения по умолчанию.
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')
        
        # Значения по умолчанию
        default_settings = {
            "font_size": 18,
            "row_height": 60
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    table_settings = config.get('table_settings', {})
                    
                    # Объединяем с настройками по умолчанию (приоритет у config файла)
                    result = default_settings.copy()
                    result.update(table_settings)
                    return result
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f'Ошибка при чтении настроек таблицы: {e}')
                return default_settings
        
        return default_settings
    
    def check_connection_status(self):
        """Проверяет статус подключения к Telegram."""
        if not self.api_id or not self.api_hash:
            return
        
        # Запускаем проверку в отдельном потоке
        thread = threading.Thread(target=self.check_status_thread)
        thread.daemon = True
        thread.start()
    
    def check_status_thread(self):
        """Поток для проверки статуса авторизации."""
        try:
            manager = TelegramManager(self.api_id, self.api_hash)
            
            # Используем метод connect() который управляет подключением
            # Проверяем авторизацию через метод connect()
            success, message = manager.connect()
            is_authorized = success
            
            if is_authorized:
                self.telegram_manager = manager
                self.after(0, lambda: self.connection_status.configure(
                    text="Подключено",
                    text_color="green"
                ))
                self.after(0, lambda: self.connect_button.configure(
                    text="Подключено",
                    state="normal"
                ))
            else:
                # Не авторизован - отключаемся
                manager.disconnect()
                self.after(0, lambda: self.connection_status.configure(
                    text="Не подключено",
                    text_color="orange"
                ))
                self.after(0, lambda: self.connect_button.configure(
                    text="Подключиться",
                    state="normal"
                ))
        
        except Exception as e:
            # Ошибка при проверке - считаем что не подключено
            self.after(0, lambda: self.connection_status.configure(
                text="Не подключено",
                text_color="orange"
            ))
            self.after(0, lambda: self.connect_button.configure(
                text="Подключиться",
                state="normal"
            ))
    
    def create_widgets(self):
        """Создает все виджеты интерфейса."""
        
        # Главный контейнер
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Фрейм для кнопки подключения (наверху)
        top_frame = ctk.CTkFrame(main_frame)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # Кнопка "Подключиться"
        self.connect_button = ctk.CTkButton(
            top_frame,
            text="Подключиться",
            command=self.on_connect_clicked,
            font=ctk.CTkFont(size=14),
            width=150,
            height=35,
            fg_color="#0066cc",
            hover_color="#0052a3"
        )
        self.connect_button.pack(side="left", padx=10, pady=10)
        
        # Кнопка "Обновить"
        self.refresh_button = ctk.CTkButton(
            top_frame,
            text="Обновить",
            command=self.on_refresh_clicked,
            font=ctk.CTkFont(size=14),
            width=150,
            height=35
        )
        self.refresh_button.pack(side="left", padx=10, pady=10)
        
        # Статус подключения - по умолчанию "Не подключено"
        # Реальный статус будет проверен после создания UI
        self.connection_status = ctk.CTkLabel(
            top_frame,
            text="Не подключено",
            font=ctk.CTkFont(size=12),
            text_color="orange"
        )
        self.connection_status.pack(side="left", padx=20)
        
        # Заголовок
        title_label = ctk.CTkLabel(
            main_frame,
            text="Чаты и каналы Telegram",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(10, 20))
        
        # Фрейм для таблицы
        table_frame = ctk.CTkFrame(main_frame)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Создание таблицы (Treeview)
        self.create_table(table_frame)
        
        # Фрейм для статус-бара
        status_frame = ctk.CTkFrame(main_frame)
        status_frame.pack(fill="x", padx=10, pady=10)
        
        # Статус-бар
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Готово",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.pack(side="left", padx=20)
    
    def create_table(self, parent):
        """Создает таблицу для отображения чатов."""
        
        # Создание Treeview с темной темой
        style = ttk.Style()
        style.theme_use("clam")
        
        # Настройка темной темы для Treeview
        # Используем настройки из конфига
        font_size = self.table_settings.get("font_size", 18)
        row_height = self.table_settings.get("row_height", 60)
        
        style.configure(
            "Treeview",
            background="#212121",
            foreground="white",
            fieldbackground="#212121",
            bordercolor="#333333",
            borderwidth=1,
            font=("TkDefaultFont", font_size),
            rowheight=row_height
        )
        style.configure(
            "Treeview.Heading",
            background="#1a1a1a",
            foreground="white",
            relief="flat",
            borderwidth=1,
            font=("TkDefaultFont", font_size)
        )
        style.map(
            "Treeview",
            background=[("selected", "#0066cc")],
            foreground=[("selected", "white")]
        )
        
        # Создание Treeview
        columns = tuple(self.column_config.keys())
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", height=20)
        
        # Настройка колонок из конфига
        for col_name, col_settings in self.column_config.items():
            heading_text = col_settings.get("heading", col_name)
            width = col_settings.get("width", 100)
            anchor = col_settings.get("anchor", "w")
            
            self.tree.heading(col_name, text=heading_text)
            # Применяем ширину из конфига
            self.tree.column(col_name, width=width, anchor=anchor, stretch=False)
        
        # Скроллбары
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Размещение виджетов
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        # Настройка grid weights
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        # Привязка события клика по столбцу "Действия"
        self.tree.bind("<Button-1>", self._on_tree_click)
    
    def refresh_table(self):
        """Обновляет таблицу данными из базы данных."""
        # Перезагружаем конфиг перед обновлением таблицы
        self.column_config = self.load_column_config()
        self.table_settings = self.load_table_settings()
        
        # Обновляем стили таблицы с новыми настройками
        style = ttk.Style()
        font_size = self.table_settings.get("font_size", 18)
        row_height = self.table_settings.get("row_height", 60)
        
        style.configure(
            "Treeview",
            font=("TkDefaultFont", font_size),
            rowheight=row_height
        )
        style.configure(
            "Treeview.Heading",
            font=("TkDefaultFont", font_size)
        )
        
        # Обновляем ширины столбцов из конфига
        for col_name, col_settings in self.column_config.items():
            width = col_settings.get("width", 100)
            anchor = col_settings.get("anchor", "w")
            self.tree.column(col_name, width=width, anchor=anchor, stretch=False)
        
        # Очистка таблицы
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Получение данных из БД
        chats = get_chats_for_display()
        
        # Функция для переноса текста (как в Excel) с учетом ширины столбца
        def wrap_text(text, column_width, font_size):
            """Разбивает длинный текст на несколько строк с учетом ширины столбца."""
            if not text:
                return "", 1
            
            text_str = str(text)
            # Приблизительный расчет: один символ занимает примерно font_size * 0.6 пикселей
            # Учитываем отступы (примерно 10 пикселей с каждой стороны)
            available_width = column_width - 20
            chars_per_line = max(1, int(available_width / (font_size * 0.6)))
            
            words = text_str.split()
            lines = []
            current_line = []
            current_length = 0
            
            for word in words:
                word_len = len(word)
                # Если слово само по себе длиннее максимума, разбиваем его
                if word_len > chars_per_line:
                    if current_line:
                        lines.append(' '.join(current_line))
                        current_line = []
                    # Разбиваем длинное слово
                    for i in range(0, word_len, chars_per_line):
                        lines.append(word[i:i+chars_per_line])
                    current_length = 0
                elif current_length + word_len + 1 <= chars_per_line:
                    current_line.append(word)
                    current_length += word_len + 1
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = word_len
            
            if current_line:
                lines.append(' '.join(current_line))
            
            num_lines = len(lines) if lines else 1
            return '\n'.join(lines), num_lines
        
        # Заполнение таблицы в соответствии с порядком столбцов из конфига
        column_order = list(self.column_config.keys())
        
        # Сначала проходим по всем данным, чтобы найти максимальное количество строк
        max_lines_per_row = 1
        row_data = []
        
        for tg_id, title, categories in chats:
            row_max_lines = 1
            row_values = []
            
            for col_name in column_order:
                if col_name == "ID чата по ТГ":
                    row_values.append((str(tg_id), 1))
                elif col_name == "Название":
                    # Получаем ширину столбца
                    col_width = self.column_config[col_name].get("width", 200)
                    wrapped_title, num_lines = wrap_text(title, col_width, font_size)
                    row_values.append((wrapped_title, num_lines))
                    row_max_lines = max(row_max_lines, num_lines)
                elif col_name == "Категории":
                    # Получаем ширину столбца
                    col_width = self.column_config[col_name].get("width", 300)
                    wrapped_categories, num_lines = wrap_text(categories, col_width, font_size)
                    row_values.append((wrapped_categories, num_lines))
                    row_max_lines = max(row_max_lines, num_lines)
                elif col_name == "Действия":
                    row_values.append(("+", 1))
                else:
                    row_values.append(("", 1))
            
            row_data.append(row_values)
            max_lines_per_row = max(max_lines_per_row, row_max_lines)
        
        # Устанавливаем динамическую высоту строки на основе максимального количества строк
        dynamic_row_height = row_height * max_lines_per_row
        style.configure(
            "Treeview",
            font=("TkDefaultFont", font_size),
            rowheight=dynamic_row_height
        )
        
        # Вставляем данные в таблицу
        for row_values in row_data:
            values_tuple = tuple(val[0] for val in row_values)
            self.tree.insert("", "end", values=values_tuple)
        
        # Обновление статуса
        self.status_label.configure(text=f"Загружено чатов: {len(chats)}")
    
    def on_refresh_clicked(self):
        """
        Обработчик нажатия кнопки "Обновить".
        Запускает обновление данных в отдельном потоке, чтобы не блокировать UI.
        """
        # Отключаем кнопку на время обновления
        self.refresh_button.configure(state="disabled", text="Обновление...")
        self.status_label.configure(text="Подключение к Telegram...")
        
        # Запускаем обновление в отдельном потоке
        thread = threading.Thread(target=self.update_data_thread)
        thread.daemon = True
        thread.start()
    
    def update_data_thread(self):
        """
        Обновляет данные в отдельном потоке.
        Сначала обновляет данные в БД, затем обновляет UI в главном потоке.
        """
        try:
            # Проверяем наличие API credentials
            if not self.api_id or not self.api_hash:
                self.after(0, lambda: self.status_label.configure(
                    text="Ошибка: сначала подключитесь через кнопку 'Подключиться'"
                ))
                self.after(0, lambda: self.refresh_button.configure(
                    state="normal", text="Обновить"
                ))
                self.after(0, lambda: messagebox.showwarning(
                    "Предупреждение",
                    "Сначала подключитесь через кнопку 'Подключиться'"
                ))
                return
            
            # Используем существующий менеджер или создаем новый
            if not self.telegram_manager:
                manager = TelegramManager(self.api_id, self.api_hash)
                self.telegram_manager = manager
            else:
                manager = self.telegram_manager
            
            # Проверяем подключение и подключаемся если нужно
            self.after(0, lambda: self.status_label.configure(
                text="Подключение к Telegram..."
            ))
            
            # Подключаемся без запроса данных (сессия должна быть сохранена)
            success, message = manager.connect()
            if not success:
                # Если требуется авторизация, сообщаем пользователю
                if message in ["phone", "code", "password"]:
                    self.after(0, lambda: self.status_label.configure(
                        text="Требуется авторизация. Используйте кнопку 'Подключиться'"
                    ))
                    self.after(0, lambda: self.refresh_button.configure(
                        state="normal", text="Обновить"
                    ))
                    self.after(0, lambda: messagebox.showwarning(
                        "Требуется авторизация",
                        "Сначала подключитесь через кнопку 'Подключиться'"
                    ))
                else:
                    self.after(0, lambda: self.status_label.configure(
                        text=f"Ошибка подключения: {message}"
                    ))
                    self.after(0, lambda: self.refresh_button.configure(
                        state="normal", text="Обновить"
                    ))
                return
            
            # Получаем список чатов
            self.after(0, lambda: self.status_label.configure(
                text="Получение списка чатов..."
            ))
            
            chats = manager.get_chats_and_channels()
            
            # Сохраняем в базу данных
            self.after(0, lambda: self.status_label.configure(
                text="Сохранение в базу данных..."
            ))
            
            save_chats(chats)
            
            # Обновляем таблицу в главном потоке
            self.after(0, self.refresh_table)
            self.after(0, lambda: self.status_label.configure(
                text=f"Обновлено! Загружено чатов: {len(chats)}"
            ))
            
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            self.after(0, lambda: self.status_label.configure(text=error_msg))
        
        finally:
            # Включаем кнопку обратно
            self.after(0, lambda: self.refresh_button.configure(
                state="normal", text="Обновить"
            ))
    
    def show_api_credentials_dialog(self):
        """
        Показывает диалоговое окно для ввода API_ID и API_HASH.
        Возвращает кортеж (api_id, api_hash) или None при отмене.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ввод API credentials")
        dialog.geometry("550x350")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = {'api_id': None, 'api_hash': None, 'confirmed': False}
        
        # Главный контейнер
        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Заголовок
        title_label = ctk.CTkLabel(
            main_container,
            text="Введите данные Telegram API",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(10, 10))
        
        # Информационный текст
        info_label = ctk.CTkLabel(
            main_container,
            text="Получите API_ID и API_HASH на https://my.telegram.org/auth",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.pack(pady=(0, 20))
        
        # Фрейм для полей ввода
        input_frame = ctk.CTkFrame(main_container)
        input_frame.pack(fill="x", padx=20, pady=10)
        
        # Поле для API_ID
        api_id_label = ctk.CTkLabel(
            input_frame,
            text="API ID:",
            width=120,
            anchor="w",
            font=ctk.CTkFont(size=13)
        )
        api_id_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        api_id_entry = ctk.CTkEntry(input_frame, width=300, font=ctk.CTkFont(size=13))
        api_id_entry.grid(row=0, column=1, padx=15, pady=15, sticky="ew")
        
        # Поле для API_HASH
        api_hash_label = ctk.CTkLabel(
            input_frame,
            text="API Hash:",
            width=120,
            anchor="w",
            font=ctk.CTkFont(size=13)
        )
        api_hash_label.grid(row=1, column=0, padx=15, pady=15, sticky="w")
        
        api_hash_entry = ctk.CTkEntry(input_frame, width=300, show="*", font=ctk.CTkFont(size=13))
        api_hash_entry.grid(row=1, column=1, padx=15, pady=15, sticky="ew")
        
        input_frame.grid_columnconfigure(1, weight=1)
        
        def on_ok():
            api_id = api_id_entry.get().strip()
            api_hash = api_hash_entry.get().strip()
            
            if not api_id or not api_hash:
                messagebox.showerror("Ошибка", "Пожалуйста, заполните оба поля")
                return
            
            try:
                # Проверяем, что API_ID - это число
                int(api_id)
            except ValueError:
                messagebox.showerror("Ошибка", "API_ID должен быть числом")
                return
            
            result['api_id'] = api_id
            result['api_hash'] = api_hash
            result['confirmed'] = True
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        # Фрейм для кнопок внизу
        button_frame = ctk.CTkFrame(main_container)
        button_frame.pack(fill="x", padx=20, pady=(20, 10), side="bottom")
        
        ok_button = ctk.CTkButton(
            button_frame,
            text="Сохранить",
            command=on_ok,
            width=180,
            height=40,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        ok_button.pack(side="left", padx=10, pady=10, expand=True)
        
        cancel_button = ctk.CTkButton(
            button_frame,
            text="Отмена",
            command=on_cancel,
            width=180,
            height=40,
            fg_color="gray",
            hover_color="darkgray",
            font=ctk.CTkFont(size=14)
        )
        cancel_button.pack(side="left", padx=10, pady=10, expand=True)
        
        # Фокус на первое поле
        dialog.after(100, api_id_entry.focus)
        
        # Ожидаем закрытия диалога
        dialog.wait_window()
        
        if result['confirmed']:
            return (result['api_id'], result['api_hash'])
        return None
    
    def on_connect_clicked(self):
        """Обработчик нажатия кнопки 'Подключиться'."""
        # Показываем диалог для ввода API credentials
        credentials = self.show_api_credentials_dialog()
        
        if credentials:
            api_id, api_hash = credentials
            
            # Сохраняем в файл
            try:
                save_api_credentials(api_id, api_hash)
                
                # Сохраняем в переменные приложения
                self.api_id = api_id
                self.api_hash = api_hash
                
                # Сразу запускаем процесс подключения к Telegram
                # Это вызовет запрос номера телефона и кода подтверждения
                self.connect_to_telegram()
            
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить credentials: {str(e)}")
                # Включаем кнопку обратно в случае ошибки
                self.connect_button.configure(state="normal", text="Подключиться")
    
    def connect_to_telegram(self):
        """Подключается к Telegram аккаунту."""
        if not self.api_id or not self.api_hash:
            self.connection_status.configure(
                text="Не подключено",
                text_color="orange"
            )
            messagebox.showwarning(
                "Предупреждение",
                "Сначала введите API credentials через кнопку 'Подключиться'"
            )
            return
        
        # Отключаем кнопку подключения
        self.connect_button.configure(state="disabled", text="Подключение...")
        self.connection_status.configure(text="Подключение...", text_color="orange")
        
        # Небольшая задержка для обновления UI
        self.after(100, lambda: self.start_connect_thread())
    
    def start_connect_thread(self):
        """Запускает поток подключения."""
        thread = threading.Thread(target=self.connect_thread)
        thread.daemon = True
        thread.start()
    
    def connect_thread(self):
        """Поток для подключения к Telegram."""
        try:
            # Создаем менеджер
            manager = TelegramManager(self.api_id, self.api_hash)
            self.telegram_manager = manager
            
            # Подключаемся (без параметров - проверит авторизацию)
            self.after(0, lambda: self.connection_status.configure(
                text="Проверка авторизации...",
                text_color="orange"
            ))
            
            # Вызываем connect() без параметров - он проверит авторизацию
            success, message = manager.connect()
            
            if success:
                # Уже подключено
                self.after(0, lambda: self.connection_status.configure(
                    text="Подключено",
                    text_color="green"
                ))
                self.after(0, lambda: self.connect_button.configure(
                    state="normal",
                    text="Подключено"
                ))
                self.after(0, lambda: self.status_label.configure(
                    text="Подключено успешно"
                ))
                self.after(0, lambda: messagebox.showinfo("Успешно", "Подключение к Telegram выполнено успешно!"))
            else:
                # Требуется авторизация
                if message == "phone":
                    # Запрашиваем номер телефона через диалог
                    self.after(0, lambda: self.connection_status.configure(
                        text="Требуется номер телефона",
                        text_color="orange"
                    ))
                    self.after(200, self.request_phone_dialog)
                elif message == "code":
                    # Запрашиваем код через диалог (если уже есть номер телефона)
                    if self.current_phone:
                        self.after(0, lambda: self.request_code_dialog(self.current_phone))
                    else:
                        self.after(0, self.request_phone_dialog)
                elif message == "password":
                    # Запрашиваем пароль 2FA через диалог
                    if self.current_phone:
                        self.after(0, lambda: self.request_password_dialog(self.current_phone))
                    else:
                        self.after(0, self.request_phone_dialog)
                else:
                    # Ошибка
                    self.after(0, lambda: self.connection_status.configure(
                        text="Не подключено",
                        text_color="orange"
                    ))
                    self.after(0, lambda: self.connect_button.configure(
                        state="normal",
                        text="Подключиться"
                    ))
                    self.after(0, lambda: self.status_label.configure(
                        text="Ошибка подключения"
                    ))
                    self.after(0, lambda: messagebox.showerror("Ошибка", message))
        
        except Exception as e:
            error_msg = f"Ошибка подключения: {str(e)}"
            self.after(0, lambda: self.connection_status.configure(
                text="Не подключено",
                text_color="orange"
            ))
            self.after(0, lambda: self.connect_button.configure(
                state="normal",
                text="Подключиться"
            ))
            self.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
    
    def request_phone_dialog(self):
        """Диалог для ввода номера телефона."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ввод номера телефона")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        phone_number = {'value': None, 'confirmed': False}
        
        ctk.CTkLabel(
            dialog,
            text="Введите номер телефона:",
            font=ctk.CTkFont(size=14)
        ).pack(pady=20)
        
        phone_entry = ctk.CTkEntry(dialog, width=300)
        phone_entry.pack(pady=10)
        phone_entry.focus()
        
        def on_ok():
            phone = phone_entry.get().strip()
            if phone:
                phone_number['value'] = phone
                phone_number['confirmed'] = True
                dialog.destroy()
        
        def on_enter(event):
            on_ok()
        
        phone_entry.bind('<Return>', on_enter)
        
        button = ctk.CTkButton(dialog, text="OK", command=on_ok, width=100)
        button.pack(pady=10)
        
        dialog.wait_window()
        
        if phone_number['confirmed']:
            self.current_phone = phone_number['value']
            # Продолжаем подключение с номером телефона
            thread = threading.Thread(
                target=lambda: self.continue_connection(self.current_phone, None, None)
            )
            thread.daemon = True
            thread.start()
    
    def request_code_dialog(self, phone):
        """Диалог для ввода кода подтверждения."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ввод кода подтверждения")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        code_value = {'value': None, 'confirmed': False}
        
        ctk.CTkLabel(
            dialog,
            text="Введите код из Telegram:",
            font=ctk.CTkFont(size=14)
        ).pack(pady=20)
        
        code_entry = ctk.CTkEntry(dialog, width=300)
        code_entry.pack(pady=10)
        code_entry.focus()
        
        def on_ok():
            code = code_entry.get().strip()
            if code:
                code_value['value'] = code
                code_value['confirmed'] = True
                dialog.destroy()
        
        def on_enter(event):
            on_ok()
        
        code_entry.bind('<Return>', on_enter)
        
        button = ctk.CTkButton(dialog, text="OK", command=on_ok, width=100)
        button.pack(pady=10)
        
        dialog.wait_window()
        
        if code_value['confirmed']:
            # Продолжаем подключение с кодом
            thread = threading.Thread(
                target=lambda: self.continue_connection(phone, code_value['value'], None)
            )
            thread.daemon = True
            thread.start()
    
    def request_password_dialog(self, phone):
        """Диалог для ввода пароля 2FA."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ввод пароля 2FA")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        password_value = {'value': None, 'confirmed': False}
        
        ctk.CTkLabel(
            dialog,
            text="Введите пароль двухфакторной аутентификации:",
            font=ctk.CTkFont(size=14)
        ).pack(pady=20)
        
        password_entry = ctk.CTkEntry(dialog, width=300, show="*")
        password_entry.pack(pady=10)
        password_entry.focus()
        
        def on_ok():
            password = password_entry.get().strip()
            if password:
                password_value['value'] = password
                password_value['confirmed'] = True
                dialog.destroy()
        
        def on_enter(event):
            on_ok()
        
        password_entry.bind('<Return>', on_enter)
        
        button = ctk.CTkButton(dialog, text="OK", command=on_ok, width=100)
        button.pack(pady=10)
        
        dialog.wait_window()
        
        if password_value['confirmed']:
            # Продолжаем подключение с паролем
            thread = threading.Thread(
                target=lambda: self.continue_connection(phone, None, password_value['value'])
            )
            thread.daemon = True
            thread.start()
    
    def continue_connection(self, phone, code, password):
        """Продолжает процесс подключения с введенными данными."""
        try:
            if self.telegram_manager:
                self.current_phone = phone
                success, message = self.telegram_manager.connect(phone, code, password)
                
                if success:
                    self.after(0, lambda: self.connection_status.configure(
                        text="Подключено",
                        text_color="green"
                    ))
                    self.after(0, lambda: self.connect_button.configure(
                        state="normal",
                        text="Подключено"
                    ))
                    self.after(0, lambda: messagebox.showinfo("Успешно", "Подключение выполнено!"))
                elif message == "code":
                    self.after(0, lambda: self.request_code_dialog(phone))
                elif message == "password":
                    self.after(0, lambda: self.request_password_dialog(phone))
                else:
                    self.after(0, lambda: self.connection_status.configure(
                        text="Не подключено",
                        text_color="orange"
                    ))
                    self.after(0, lambda: self.connect_button.configure(
                        state="normal",
                        text="Подключиться"
                    ))
                    self.after(0, lambda: messagebox.showerror("Ошибка", message))
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            self.after(0, lambda: self.connection_status.configure(
                text="Не подключено",
                text_color="orange"
            ))
            self.after(0, lambda: self.connect_button.configure(
                state="normal",
                text="Подключиться"
            ))
            self.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
    
    def _on_tree_click(self, event):
        """Обработчик клика по таблице."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item = self.tree.identify_row(event.y)
            
            # Получаем порядок столбцов из конфига
            column_order = list(self.column_config.keys())
            
            # Определяем индекс столбца "Действия" (индекс +1, т.к. #0 - это tree column)
            try:
                actions_col_index = column_order.index("Действия") + 1
                # Проверяем, что клик был по столбцу "Действия"
                if column == f"#{actions_col_index}" and item:
                    # Получаем tg_id из значений строки
                    values = self.tree.item(item, "values")
                    # Находим индекс столбца "ID чата по ТГ"
                    tg_id_col_index = column_order.index("ID чата по ТГ")
                    if values and len(values) > tg_id_col_index:
                        try:
                            tg_id = int(values[tg_id_col_index])
                            self._show_category_dialog(tg_id)
                        except (ValueError, IndexError):
                            pass
            except ValueError:
                # Столбец "Действия" не найден в конфиге
                pass
    
    def _show_category_dialog(self, chat_tg_id):
        """Показывает мини-окошко для управления категориями чата."""
        # Получаем доступные категории
        available_categories = get_available_categories_for_chat(chat_tg_id)
        
        # Создаем окно
        dialog = ctk.CTkToplevel(self)
        dialog.title("Категория")
        dialog.geometry("320x500")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Главный контейнер
        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Заголовок
        title_label = ctk.CTkLabel(
            main_container,
            text="Категория",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 10))
        
        # Поле поиска
        search_frame = ctk.CTkFrame(main_container)
        search_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Поиск...",
            font=ctk.CTkFont(size=12)
        )
        search_entry.pack(fill="x", padx=5, pady=5)
        
        # Фрейм для списка категорий с прокруткой
        list_frame = ctk.CTkFrame(main_container)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Scrollable frame для категорий
        scrollable_frame = ctk.CTkScrollableFrame(
            list_frame,
            height=270
        )
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Словарь для хранения кнопок категорий
        category_buttons = {}
        
        def update_category_list(search_term=""):
            """Обновляет список категорий в зависимости от поиска."""
            # Удаляем старые кнопки
            for button in category_buttons.values():
                button.destroy()
            category_buttons.clear()
            
            # Получаем категории
            if search_term:
                categories = search_available_categories_for_chat(chat_tg_id, search_term)
            else:
                categories = get_available_categories_for_chat(chat_tg_id)
            
            # Создаем кнопки для категорий
            for cat_id, cat_name in categories:
                button = ctk.CTkButton(
                    scrollable_frame,
                    text=cat_name,
                    font=ctk.CTkFont(size=12),
                    anchor="w",
                    fg_color="transparent",
                    text_color="white",
                    hover_color="#333333",
                    command=lambda cid=cat_id: self._assign_category(chat_tg_id, cid, dialog)
                )
                button.pack(fill="x", padx=5, pady=2)
                category_buttons[cat_id] = button
        
        # Инициализация списка
        update_category_list()
        
        # Обработчик поиска
        def on_search_change(*args):
            search_term = search_entry.get()
            update_category_list(search_term)
        
        search_entry.bind("<KeyRelease>", on_search_change)
        
        # Кнопка "Создать категорию" в отдельном фрейме
        button_frame = ctk.CTkFrame(main_container)
        button_frame.pack(fill="x", padx=10, pady=(0, 10), side="bottom")
        
        create_button = ctk.CTkButton(
            button_frame,
            text="Создать категорию",
            font=ctk.CTkFont(size=12),
            command=lambda: self._create_category_dialog(chat_tg_id, dialog, update_category_list),
            fg_color="#0066cc",
            hover_color="#0052a3"
        )
        create_button.pack(pady=5)
    
    def _create_category_dialog(self, chat_tg_id, parent_dialog, update_callback):
        """Создает диалог для создания новой категории."""
        dialog = ctk.CTkToplevel(parent_dialog)
        dialog.title("Создать категорию")
        dialog.geometry("400x200")
        dialog.transient(parent_dialog)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Поле ввода
        name_label = ctk.CTkLabel(
            main_container,
            text="Название категории:",
            font=ctk.CTkFont(size=12)
        )
        name_label.pack(pady=(10, 5))
        
        name_entry = ctk.CTkEntry(main_container, width=250, font=ctk.CTkFont(size=12))
        name_entry.pack(pady=5)
        name_entry.focus()
        
        def on_ok():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Ошибка", "Введите название категории")
                return
            
            try:
                category_id = create_category(name)
                # Автоматически присваиваем категорию чату
                add_category_to_chat(chat_tg_id, category_id)
                # Обновляем список
                update_callback()
                # Обновляем таблицу
                self.refresh_table()
                dialog.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Ошибка", "Категория с таким названием уже существует")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать категорию: {str(e)}")
        
        def on_enter(event):
            on_ok()
        
        name_entry.bind('<Return>', on_enter)
        
        # Кнопки
        button_frame = ctk.CTkFrame(main_container)
        button_frame.pack(pady=10)
        
        ok_button = ctk.CTkButton(
            button_frame,
            text="Создать",
            command=on_ok,
            width=100,
            fg_color="#0066cc",
            hover_color="#0052a3"
        )
        ok_button.pack(side="left", padx=5)
        
        cancel_button = ctk.CTkButton(
            button_frame,
            text="Отмена",
            command=dialog.destroy,
            width=100,
            fg_color="gray",
            hover_color="darkgray"
        )
        cancel_button.pack(side="left", padx=5)
    
    def _assign_category(self, chat_tg_id, category_id, dialog):
        """Присваивает категорию чату."""
        try:
            add_category_to_chat(chat_tg_id, category_id)
            dialog.destroy()
            self.refresh_table()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось присвоить категорию: {str(e)}")


def main():
    """Точка входа в приложение."""
    app = TelegramChatsApp()
    app.mainloop()


if __name__ == "__main__":
    main()

