"""
Главный файл приложения.
Создает GUI на основе customtkinter для отображения чатов Telegram.
"""
import customtkinter as ctk
from tkinter import ttk, messagebox, PhotoImage, Menu, filedialog
import threading
import os
import sys
import sqlite3
import json
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtWidgets, QtCore

# Добавляем корневую директорию проекта в путь
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Пути к конфигам
GRAPH_SETTINGS_FILE = os.path.join(BASE_DIR, "data", "graph_settings.json")

from tg_logic import TelegramManager, save_api_credentials, load_api_credentials
from db_logic import (
    init_database,
    save_chats,
    get_chats_for_display,
    create_category,
    get_available_categories_for_chat,
    search_available_categories_for_chat,
    add_category_to_chat,
    get_last_message_id_for_chat,
    append_message_stats,
    replace_message_stats_for_chat,
    has_message_stats_for_chat,
    get_daily_message_counts,
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
        # Настраиваем окно для корректного изменения размеров
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Инициализация базы данных
        init_database()
        
        # Переменные для хранения данных Telegram
        self.api_id = None
        self.api_hash = None
        self.telegram_manager = None
        self.current_phone = None  # Номер телефона для авторизации
        # Переменные для иконок типов
        self.channel_icon = None
        self.chat_icon = None
        self._row_type_icons = []
        # Данные таблицы для фильтрации
        self.all_chats = []
        
        # Загружаем сохраненные credentials при запуске
        self.load_saved_credentials()
        
        # Загружаем настройки столбцов из config
        self.column_config = self.load_column_config()
        # Состояние видимости столбцов таблицы
        self.column_visibility = {}
        # Переменные для чекбоксов меню "Таблица"
        self.table_column_vars = {}
        # Группировка логических столбцов (Категории управляет связанными колонками)
        self.category_columns_group = [
            "Категории",
            "Редактирование категорий чата",
            "Добавление категорий чату",
        ]
        # Инициализируем состояние видимости с учётом сохранённого в конфиге
        self._init_column_visibility_state()
        
        # Загружаем настройки таблицы из config
        self.table_settings = self.load_table_settings()
        # Загружаем настройки поиска
        self.search_settings = self.load_search_settings()
        # Загружаем настройки экспорта
        self.export_settings = self.load_export_settings()
        # Загружаем настройки графика сообщений
        self.chart_settings = self.load_chart_settings()
        # Загрузка иконок типов (канал / чат)
        self._load_type_icons()
        
        # Создание меню и UI
        self.create_menu()
        self.create_widgets()
        
        # Проверяем статус подключения при запуске
        if self.api_id and self.api_hash:
            # Проверяем авторизацию в фоновом потоке
            self.check_connection_status()
        
        # Загрузка данных при запуске, если они есть в БД
        self.refresh_table()
        
        # Максимизируем окно после полной инициализации (как в окне графика)
        # Используем протокол для максимизации после первого отображения окна
        def maximize_window():
            """Максимизирует окно после его отображения."""
            try:
                self.update_idletasks()  # Обновляем информацию о размерах окна
                # Максимизируем окно (аналогично showMaximized() в окне графика)
                self.state('zoomed')  # Для Windows максимизирует окно в полноэкранном режиме
                self.update_idletasks()  # Обновляем после максимизации
            except Exception as e:
                print(f"Ошибка при максимизации окна: {e}")
        
        # Выполняем максимизацию после того, как окно отобразится
        # Используем несколько попыток с задержками, как в окне графика
        self.after(0, maximize_window)
        self.after(50, maximize_window)  # Дополнительная попытка через 50мс
        self.after(200, maximize_window)  # Дополнительная попытка через 200мс
    
    def _load_type_icons(self):
        """Загружает иконки для столбца 'Тип' и хранит ссылки, чтобы их не собирал GC."""
        try:
            channel_icon_path = os.path.join(BASE_DIR, "media", "channel_icon.png")
            chat_icon_path = os.path.join(BASE_DIR, "media", "chat_icon.png")

            # Целевой размер иконки из конфига (если указан)
            type_config = self.column_config.get("Тип", {})
            target_icon_size = type_config.get("icon_size")

            if os.path.exists(channel_icon_path):
                icon = PhotoImage(file=channel_icon_path)
                # Масштабируем только если задан icon_size и он положительный
                if isinstance(target_icon_size, int) and target_icon_size > 0:
                    orig_w = icon.width()
                    # уменьшаем иконку до ближайшего размера не больше target_icon_size
                    if orig_w > target_icon_size:
                        # коэффициент целочисленного деления для subsample
                        scale = max(1, round(orig_w / target_icon_size))
                        icon = icon.subsample(scale, scale)
                self.channel_icon = icon

            if os.path.exists(chat_icon_path):
                icon = PhotoImage(file=chat_icon_path)
                if isinstance(target_icon_size, int) and target_icon_size > 0:
                    orig_w = icon.width()
                    if orig_w > target_icon_size:
                        scale = max(1, round(orig_w / target_icon_size))
                        icon = icon.subsample(scale, scale)
                self.chat_icon = icon
        except Exception as e:
            print(f"Не удалось загрузить иконки типов: {e}")

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
        
        # Значения по умолчанию (старые имена столбцов, если нет конфига)
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
            "Количество участников": {
                "heading": "Участников",
                "width": 120,
                "anchor": "center"
            },
            "Категории": {
                "heading": "Категории",
                "width": 200,
                "anchor": "w"
            },
            "Редактирование категорий чата": {
                "heading": "",
                "width": 50,
                "anchor": "center"
            },
            "Добавление категорий чату": {
                "heading": "+",
                "width": 50,
                "anchor": "center"
            },
            "Экспорт чата": {
                "heading": "Экспорт",
                "width": 80,
                "anchor": "center"
            },
            "График сообщений": {
                "heading": "График",
                "width": 100,
                "anchor": "center"
            },
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    file_columns = config.get('table_columns', {})

                    # Если в конфиге есть описание столбцов, считаем его основным источником порядка
                    if isinstance(file_columns, dict) and file_columns:
                        result = {}
                        # Сохраняем порядок столбцов из config.json,
                        # подмешивая значения по умолчанию для отсутствующих полей
                        for key, user_settings in file_columns.items():
                            base = default_config.get(key, {})
                            merged = base.copy()
                            merged.update(user_settings or {})
                            result[key] = merged
                        return result

                    # Если секция table_columns отсутствует или пуста — используем дефолт
                    return default_config
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
    
    def load_search_settings(self):
        """
        Загружает настройки блока поиска из config.json.
        Позволяет настраивать тексты и размеры плашки поиска.
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')

        # Значения по умолчанию
        default_settings = {
            "label_text": "Поиск по чатам",
            "placeholder_text": "Поиск...",
            "font_size": 13,
            "entry_width": 300,
            "entry_height": 32
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    search_settings = config.get('search_settings', {})

                    result = default_settings.copy()
                    result.update(search_settings)
                    return result
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f'Ошибка при чтении настроек поиска: {e}')
                return default_settings

        return default_settings

    def load_export_settings(self):
        """
        Загружает настройки экспорта чатов из config.json.
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')

        default_settings = {
            "words_per_file": 50000,
            "delay_messages_chunk": 1000,
            "delay_seconds": 1.0,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    export_settings = config.get("export_settings", {}) or {}
                    result = default_settings.copy()
                    result.update(export_settings)
                    return result
            except (json.JSONDecodeError, IOError, KeyError):
                return default_settings

        return default_settings

    def load_chart_settings(self):
        """
        Загружает настройки графика сообщений из data/graph_settings.json.
        Если файл отсутствует или повреждён, используются значения по умолчанию.
        """
        default_settings = {
            "bar_color": "#1f77b4",
            "bargap": 0.15,
            "xaxis_tickangle": -45,
            "auto_open": True,
        }

        if os.path.exists(GRAPH_SETTINGS_FILE):
            try:
                with open(GRAPH_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f) or {}

                result = default_settings.copy()
                result.update(config)
                return result
            except (json.JSONDecodeError, IOError, TypeError):
                # Если файл настроек битый, тихо откатываемся к дефолтам
                return default_settings

        return default_settings

    def _format_number(self, value):
        """
        Красиво форматирует число с разделением тысяч пробелами: 1 000, 23 456 789.
        Нечисловые значения возвращаются как есть.
        """
        if value is None:
            return ""
        try:
            n = int(str(value).replace(" ", ""))
        except (TypeError, ValueError):
            return str(value)
        return f"{n:,}".replace(",", " ")
    
    def create_menu(self):
        """Создает верхнее меню приложения (в тёмной теме) с действиями подключения и обновления."""
        # Общие настройки тёмной темы для меню
        dark_bg = "#202020"
        dark_active_bg = "#333333"
        light_fg = "#ffffff"
        light_active_fg = "#ffffff"

        # Глобальные опции для всех Menu (работают в большинстве тем Tk)
        self.option_add("*Menu.background", dark_bg)
        self.option_add("*Menu.foreground", light_fg)
        self.option_add("*Menu.activeBackground", dark_active_bg)
        self.option_add("*Menu.activeForeground", light_active_fg)
        self.option_add("*Menu.relief", "flat")

        menubar = Menu(
            self,
            background=dark_bg,
            foreground=light_fg,
            activebackground=dark_active_bg,
            activeforeground=light_active_fg,
            borderwidth=0,
        )

        # Меню "Соединение" с действиями подключения и обновления
        connection_menu = Menu(
            menubar,
            tearoff=0,
            background=dark_bg,
            foreground=light_fg,
            activebackground=dark_active_bg,
            activeforeground=light_active_fg,
            borderwidth=0,
        )
        connection_menu.add_command(
            label="Подключиться...",
            command=self.on_connect_clicked
        )
        connection_menu.add_command(
            label="Обновить",
            command=self.on_refresh_clicked
        )
        menubar.add_cascade(label="Соединение", menu=connection_menu)

        # Меню "Таблица" для управления видимостью столбцов
        table_menu = Menu(
            menubar,
            tearoff=0,
            background=dark_bg,
            foreground=light_fg,
            activebackground=dark_active_bg,
            activeforeground=light_active_fg,
            borderwidth=0,
        )
        self._init_table_menu(table_menu)
        menubar.add_cascade(label="Таблица", menu=table_menu)

        # Устанавливаем меню для окна
        self.config(menu=menubar)

        # Сохраняем ссылки, если позже понадобится обновлять пункты
        self.menubar = menubar
        self.connection_menu = connection_menu
        self.table_menu = table_menu

    def _init_column_visibility_state(self):
        """
        Инициализирует состояние видимости столбцов.
        По умолчанию все столбцы включены, но если в config.json
        есть секция table_column_visibility — используем её.
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')
        saved_visibility = {}

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    saved_visibility = config.get("table_column_visibility", {}) or {}
            except (json.JSONDecodeError, IOError, KeyError):
                saved_visibility = {}

        for col_name in self.column_config.keys():
            if col_name in saved_visibility:
                # Явно сохранённое состояние из конфига
                self.column_visibility[col_name] = bool(saved_visibility.get(col_name, True))
            elif col_name not in self.column_visibility:
                # Если уже есть сохранённое состояние в объекте — не перезаписываем
                self.column_visibility[col_name] = True

    def _init_table_menu(self, table_menu: Menu):
        """
        Заполняет меню 'Таблица' пунктами для управления видимостью столбцов.
        Использует heading из конфига, где он задан.
        Столбцы 'Редактирование категорий чата' и 'Добавление категорий чату'
        управляются совместно с 'Категории' и отдельно в меню не выводятся.
        """
        self.table_column_vars.clear()

        for col_name, col_settings in self.column_config.items():
            # Технические столбцы категорий управляются пунктом "Категории"
            if col_name in (
                "Редактирование категорий чата",
                "Добавление категорий чату",
            ):
                continue

            # Текст пункта меню берём из heading, если он не пустой,
            # иначе используем исходное имя столбца.
            heading = col_settings.get("heading")
            label_text = heading if isinstance(heading, str) and heading.strip() else col_name

            # Для "Категории" уточняем в названии, что это группа
            if col_name == "Категории":
                label_text = "Категории"

            # Начальное значение чекбокса — из состояния видимости
            initial = self.column_visibility.get(col_name, True)
            var = ctk.BooleanVar(value=initial)
            self.table_column_vars[col_name] = var

            table_menu.add_checkbutton(
                label=label_text,
                variable=var,
                command=lambda name=col_name: self._toggle_table_column(name),
            )

    def _toggle_table_column(self, logical_name: str):
        """
        Обработчик переключения чекбокса в меню 'Таблица'.
        logical_name — логическое имя столбца из column_config.

        Особый случай: 'Категории' управляет одновременно
        столбцами 'Категории', 'Редактирование категорий чата'
        и 'Добавление категорий чату'.
        """
        # Значение чекбокса для логического имени
        if logical_name in self.table_column_vars:
            is_visible = bool(self.table_column_vars[logical_name].get())
        else:
            is_visible = True

        if logical_name == "Категории":
            # Применяем одно состояние ко всей группе
            for name in self.category_columns_group:
                self.column_visibility[name] = is_visible
            # Для технических столбцов отдельного чекбокса нет,
            # поэтому только обновляем таблицу.
        else:
            self.column_visibility[logical_name] = is_visible

        # Применяем новое состояние к Treeview
        self._apply_column_visibility()
        # И сохраняем актуальное состояние в config.json
        self._save_column_visibility_to_config()

    def _apply_column_visibility(self):
        """
        Применяет состояние self.column_visibility к колонкам Treeview.
        Реализовано через изменение ширины/минимальной ширины:
        скрытый столбец получает width=0, minwidth=0.
        """
        if not hasattr(self, "tree"):
            return

        column_order = list(self.column_config.keys())
        type_column_name = "Тип"

        for col_name in column_order:
            visible = self.column_visibility.get(col_name, True)

            # Берём базовую ширину из конфига
            col_settings = self.column_config.get(col_name, {})
            base_width = col_settings.get("width", 100)
            anchor = col_settings.get("anchor", "w")

            # Определяем идентификатор колонки в Treeview
            if col_name == type_column_name:
                tree_col_id = "#0"
            else:
                tree_col_id = col_name

            if visible:
                self.tree.column(
                    tree_col_id,
                    width=base_width,
                    minwidth=base_width,
                    anchor=anchor,
                    stretch=False,
                )
            else:
                # Полностью прячем столбец
                self.tree.column(
                    tree_col_id,
                    width=0,
                    minwidth=0,
                    stretch=False,
                )

    def _save_column_visibility_to_config(self):
        """
        Сохраняет текущее состояние self.column_visibility в секцию
        table_column_visibility файла config.json.
        Не трогает остальные настройки (столбцы, поиск, таблица и т.п.).
        """
        config_file = os.path.join(BASE_DIR, 'data', 'config.json')
        config = {}

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                # Если конфиг битый — начинаем с пустого и перезаписываем только видимость
                config = {}

        visibility_to_save = {}
        for col_name in self.column_config.keys():
            visibility_to_save[col_name] = bool(self.column_visibility.get(col_name, True))

        config["table_column_visibility"] = visibility_to_save

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except IOError:
            # Не ломаем работу приложения, если не удалось сохранить
            pass
    
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
                # Получаем отображаемое имя аккаунта (если доступно)
                account_name = None
                try:
                    account_name = manager.get_current_user_name()
                except Exception:
                    account_name = None
                status_text = f'Подключено к "{account_name}"' if account_name else "Подключено"
                self.after(0, lambda st=status_text: self.connection_status.configure(
                    text=st,
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
        
        # Верхняя панель управления (как тулбар) с блоком статуса
        top_frame = ctk.CTkFrame(main_frame)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # Техническая кнопка "Подключиться" (не отображается в UI),
        # используется только для переиспользования существующей логики .configure(...)
        self.connect_button = ctk.CTkButton(
            top_frame,
            text="Подключиться",
            command=self.on_connect_clicked,
            font=ctk.CTkFont(size=14),
            width=0,
            height=0
        )
        # Не размещаем кнопку в макете, чтобы не показывать ее пользователю
        
        # Статус подключения - по умолчанию "Не подключено"
        # Реальный статус будет проверен после создания UI
        self.connection_status = ctk.CTkLabel(
            top_frame,
            text="Не подключено",
            font=ctk.CTkFont(size=12),
            text_color="orange"
        )
        self.connection_status.pack(side="left", padx=20, pady=10)

        # Скрытая техническая кнопка "Обновить" — используется логикой on_refresh_clicked,
        # но не отображается в интерфейсе (вместо нее используется пункт меню).
        self.refresh_button = ctk.CTkButton(
            top_frame,
            text="Обновить",
            command=self.on_refresh_clicked,
            font=ctk.CTkFont(size=14),
            width=0,
            height=0
        )
        # Не размещаем кнопку в layout

        # Блок поиска по чатам под статусом
        search_frame = ctk.CTkFrame(main_frame)
        search_frame.pack(fill="x", padx=10, pady=(10, 0))

        search_label = ctk.CTkLabel(
            search_frame,
            text=self.search_settings.get("label_text", "Поиск по чатам"),
            font=ctk.CTkFont(size=self.search_settings.get("label_font_size", 12))
        )
        search_label.pack(anchor="w", padx=10, pady=(8, 2))

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text=self.search_settings.get("placeholder_text", "Поиск..."),
            textvariable=self.search_var,
            font=ctk.CTkFont(size=self.search_settings.get("font_size", 13)),
            width=self.search_settings.get("entry_width", 300),
            height=self.search_settings.get("entry_height", 32)
        )
        # Не растягиваем по всей ширине, чтобы уважать width из конфига
        self.search_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_change)
        
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
        # В Tkinter иконка может отображаться только в "деревянной" колонке #0,
        # поэтому используем ее под столбец "Тип", а остальные выводим как обычные колонки.
        column_order = list(self.column_config.keys())
        type_column_name = "Тип"
        display_columns = [name for name in column_order if name != type_column_name]

        self.tree = ttk.Treeview(
            parent,
            columns=tuple(display_columns),
            show="tree headings",
            height=20
        )

        # Настройка колонки типа в #0
        if type_column_name in self.column_config:
            type_settings = self.column_config[type_column_name]
            type_heading = type_settings.get("heading", type_column_name)
            type_width = type_settings.get("width", 60)
            type_anchor = type_settings.get("anchor", "center")

            self.tree.heading("#0", text=type_heading)
            self.tree.column("#0", width=type_width, anchor=type_anchor, stretch=False)
        else:
            # Если по какой-то причине в конфиге нет "Тип", скрываем #0
            self.tree.heading("#0", text="")
            self.tree.column("#0", width=0, stretch=False)

        # Настройка остальных колонок из конфига
        for col_name in display_columns:
            col_settings = self.column_config.get(col_name, {})
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
        
        # Привязка события клика по таблице (для обработки столбцов действий)
        self.tree.bind("<Button-1>", self._on_tree_click)
        # Привязка события двойного клика по строке для копирования значений
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # После создания таблицы применяем актуальное состояние видимости столбцов
        self._apply_column_visibility()
    
    def refresh_table(self, chats=None):
        """Обновляет таблицу данными.
        
        Если chats не передан, данные берутся из базы данных и кэшируются
        в self.all_chats. Если передан список chats, используется он
        (для фильтрации/поиска).
        """
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
        column_order = list(self.column_config.keys())
        type_column_name = "Тип"
        display_columns = [name for name in column_order if name != type_column_name]

        for col_name, col_settings in self.column_config.items():
            width = col_settings.get("width", 100)
            anchor = col_settings.get("anchor", "w")
            if col_name == type_column_name:
                # Столбец типа — это колонка #0
                self.tree.column("#0", width=width, anchor=anchor, stretch=False)
            elif col_name in display_columns:
                self.tree.column(col_name, width=width, anchor=anchor, stretch=False)

        # Переинициализируем состояние видимости (на случай изменения конфига извне)
        self._init_column_visibility_state()
        # И применяем его к таблице (скрывая/показывая столбцы)
        self._apply_column_visibility()
        
        # Получение данных из БД, если не переданы явно
        if chats is None:
            chats = get_chats_for_display()
            # Кэшируем полные данные для последующей фильтрации
            self.all_chats = list(chats)

        # Очистка таблицы
        for item in self.tree.get_children():
            self.tree.delete(item)
        
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
        type_column_name = "Тип"
        display_columns = [name for name in column_order if name != type_column_name]
        
        # Сначала проходим по всем данным, чтобы найти максимальное количество строк
        max_lines_per_row = 1
        row_data = []
        # Очищаем ссылки на иконки строк
        self._row_type_icons.clear()
        
        for tg_id, title, participants_count, categories, chat_type in chats:
            row_max_lines = 1
            row_values = []
            row_icon = None
            
            for col_name in column_order:
                if col_name == type_column_name:
                    # Первый столбец: показываем только иконку, без текста
                    if chat_type == "channel" and self.channel_icon is not None:
                        row_icon = self.channel_icon
                    elif chat_type == "chat" and self.chat_icon is not None:
                        row_icon = self.chat_icon
                elif col_name == "ID чата по ТГ":
                    # ID чата отображаем без разделения тысяч, как есть
                    row_values.append((str(tg_id), 1))
                elif col_name == "Название":
                    # Получаем ширину столбца
                    col_width = self.column_config[col_name].get("width", 200)
                    wrapped_title, num_lines = wrap_text(title, col_width, font_size)
                    row_values.append((wrapped_title, num_lines))
                    row_max_lines = max(row_max_lines, num_lines)
                elif col_name == "Количество участников":
                    # Количество участников отображаем как число по центру
                    value = self._format_number(participants_count)
                    row_values.append((value, 1))
                elif col_name == "Категории":
                    # Получаем ширину столбца
                    col_width = self.column_config[col_name].get("width", 300)
                    wrapped_categories, num_lines = wrap_text(categories, col_width, font_size)
                    row_values.append((wrapped_categories, num_lines))
                    row_max_lines = max(row_max_lines, num_lines)
                elif col_name == "Редактирование категорий чата":
                    # Столбец с кнопкой редактирования категорий (иконка-карандаш)
                    row_values.append(("✎", 1))
                elif col_name == "Добавление категорий чату":
                    row_values.append(("+", 1))
                elif col_name == "Экспорт чата":
                    # Столбец с кнопкой экспорта чата
                    row_values.append(("⭳", 1))
                elif col_name == "График сообщений":
                    # Столбец с кнопкой графика сообщений
                    row_values.append(("📈", 1))
                else:
                    row_values.append(("", 1))
            
            row_data.append((row_values, row_icon))
            max_lines_per_row = max(max_lines_per_row, row_max_lines)
        
        # Устанавливаем динамическую высоту строки на основе максимального количества строк
        dynamic_row_height = row_height * max_lines_per_row
        style.configure(
            "Treeview",
            font=("TkDefaultFont", font_size),
            rowheight=dynamic_row_height
        )
        
        # Вставляем данные в таблицу
        for row_values, row_icon in row_data:
            values_tuple = tuple(val[0] for val in row_values)
            # Передаем параметр image только если иконка реально есть,
            # иначе Tcl ругается на пустое значение для -image
            if row_icon is not None:
                item_id = self.tree.insert("", "end", values=values_tuple, image=row_icon)
                self._row_type_icons.append((item_id, row_icon))
            else:
                item_id = self.tree.insert("", "end", values=values_tuple)
        
        # Обновление статуса
        self.status_label.configure(
            text=f"Загружено чатов: {self._format_number(len(chats))}"
        )
    
    def on_refresh_clicked(self):
        """
        Обработчик нажатия кнопки "Обновить".
        Запускает обновление данных в отдельном потоке, чтобы не блокировать UI.
        """
        # Отключаем кнопку на время обновления (техническая, может быть скрыта)
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="disabled", text="Обновление...")
        self.status_label.configure(text="Подключение к Telegram...")
        
        # Запускаем обновление в отдельном потоке
        thread = threading.Thread(target=self.update_data_thread)
        thread.daemon = True
        thread.start()

    def on_search_change(self, event=None):
        """
        Обработчик изменения строки поиска.
        Фильтрует чаты по названию и ID чата.
        """
        query = (self.search_var.get() if hasattr(self, "search_var") else "").strip()
        # Если нет кэша данных или пустой запрос — показываем все данные
        if not getattr(self, "all_chats", None) or not query:
            self.refresh_table()
            return

        q_lower = query.lower()
        filtered = []
        for tg_id, title, participants_count, categories, chat_type in self.all_chats:
            # Поиск по ID
            if q_lower in str(tg_id).lower():
                filtered.append((tg_id, title, participants_count, categories, chat_type))
                continue
            # Поиск по названию
            if title and q_lower in str(title).lower():
                filtered.append((tg_id, title, participants_count, categories, chat_type))

        self.refresh_table(chats=filtered)
    
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
                if hasattr(self, "refresh_button"):
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
                if hasattr(self, "refresh_button"):
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
                text=f"Обновлено! Загружено чатов: {self._format_number(len(chats))}"
            ))
            
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            self.after(0, lambda: self.status_label.configure(text=error_msg))
        
        finally:
            # Включаем кнопку обратно
            if hasattr(self, "refresh_button"):
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
                account_name = None
                try:
                    account_name = manager.get_current_user_name()
                except Exception:
                    account_name = None
                status_text = f'Подключено к "{account_name}"' if account_name else "Подключено"
                self.after(0, lambda st=status_text: self.connection_status.configure(
                    text=st,
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
                    account_name = None
                    try:
                        account_name = self.telegram_manager.get_current_user_name()
                    except Exception:
                        account_name = None
                    status_text = f'Подключено к "{account_name}"' if account_name else "Подключено"
                    self.after(0, lambda st=status_text: self.connection_status.configure(
                        text=st,
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
            type_column_name = "Тип"
            # В Treeview колонка типа — это #0, остальные — display_columns
            display_columns = [name for name in column_order if name != type_column_name]
            
            try:
                # Находим индекс столбца с добавлением категории в display_columns
                actions_display_index = display_columns.index("Добавление категорий чату") + 1
            except ValueError:
                actions_display_index = None

            try:
                # Находим индекс столбца с редактированием категорий (если он есть) в display_columns
                edit_display_index = display_columns.index("Редактирование категорий чата") + 1
            except ValueError:
                edit_display_index = None

            try:
                # Находим индекс столбца экспорта чата (если он есть) в display_columns
                export_display_index = display_columns.index("Экспорт чата") + 1
            except ValueError:
                export_display_index = None

            try:
                # Находим индекс столбца графика сообщений (если он есть) в display_columns
                graph_display_index = display_columns.index("График сообщений") + 1
            except ValueError:
                graph_display_index = None
            
            if not item:
                return
            
            # Получаем tg_id из значений строки
            values = self.tree.item(item, "values")
            try:
                # Индекс столбца "ID чата по ТГ" в display_columns
                tg_id_col_index = display_columns.index("ID чата по ТГ")
            except ValueError:
                tg_id_col_index = None
            
            tg_id = None
            if tg_id_col_index is not None and values and len(values) > tg_id_col_index:
                try:
                    # Удаляем пробелы-разделители тысяч перед преобразованием в число
                    raw_id = str(values[tg_id_col_index]).replace(" ", "")
                    tg_id = int(raw_id)
                except (ValueError, IndexError):
                    tg_id = None
            
            # Обработка клика по столбцу добавления категории ("Действия")
            if actions_display_index is not None and column == f"#{actions_display_index}" and tg_id is not None:
                self._show_category_dialog(tg_id)
                return
            
            # Обработка клика по столбцу редактирования категорий
            if edit_display_index is not None and column == f"#{edit_display_index}" and tg_id is not None:
                self._show_edit_categories_dialog(tg_id)
                return

            # Обработка клика по столбцу экспорта чата
            if export_display_index is not None and column == f"#{export_display_index}" and tg_id is not None:
                chat_info = self._get_chat_by_id(tg_id)
                if chat_info:
                    chat_title, participants_count, categories, chat_type = chat_info
                    self._show_export_dialog(tg_id, chat_title, chat_type)
                return

            # Обработка клика по столбцу "График сообщений"
            if graph_display_index is not None and column == f"#{graph_display_index}" and tg_id is not None:
                chat_info = self._get_chat_by_id(tg_id)
                if chat_info:
                    chat_title, participants_count, categories, chat_type = chat_info
                    self._show_message_stats_chart(tg_id, chat_title, chat_type)
                return

    def _on_tree_double_click(self, event):
        """
        Копирует значение из строки по двойному клику:
        - если клик по колонке ID чата — копируется ID;
        - если клик по колонке Название — копируется название.
        """
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if not item or not column.startswith("#"):
            return

        # Восстанавливаем порядок столбцов из конфига
        column_order = list(self.column_config.keys())
        type_column_name = "Тип"
        display_columns = [name for name in column_order if name != type_column_name]

        # Индексы интересующих нас колонок
        try:
            id_display_index = display_columns.index("ID чата по ТГ")
        except ValueError:
            id_display_index = None

        try:
            title_display_index = display_columns.index("Название")
        except ValueError:
            title_display_index = None

        # Преобразуем "#N" -> индекс 0-based в display_columns
        try:
            clicked_index = int(column[1:]) - 1
        except ValueError:
            return

        # Нас интересуют только колонки ID и Название
        if clicked_index not in (id_display_index, title_display_index):
            return

        values = self.tree.item(item, "values") or ()
        if clicked_index < 0 or clicked_index >= len(values):
            return

        value_to_copy = values[clicked_index]
        if not value_to_copy:
            return

        # Копируем в буфер обмена
        try:
            self.clipboard_clear()
            self.clipboard_append(str(value_to_copy))
            # Обновляем UI, чтобы буфер гарантированно применился
            self.update()

            # Готовим текст статуса
            status_text = "Скопировано в буфер обмена"
            if clicked_index == id_display_index:
                status_text = "ID чата скопирован в буфер обмена"
            elif clicked_index == title_display_index:
                status_text = "Название чата скопировано в буфер обмена"

            if hasattr(self, "status_label"):
                self.status_label.configure(text=status_text)
        except Exception as e:
            if hasattr(self, "status_label"):
                self.status_label.configure(text=f"Не удалось скопировать: {e}")
    
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

    def _show_edit_categories_dialog(self, chat_tg_id):
        """Показывает мини-окошко со списком присвоенных категорий и возможностью удаления."""
        # Импортируем здесь, чтобы избежать циклических импортов
        from db_logic import get_chat_categories, get_all_categories, remove_category_from_chat

        dialog = ctk.CTkToplevel(self)
        dialog.title("Редактирование категорий")
        dialog.geometry("320x400")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        title_label = ctk.CTkLabel(
            main_container,
            text="Присвоенные категории",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 10))
        
        info_label = ctk.CTkLabel(
            main_container,
            text="Нажмите на крестик справа, чтобы удалить категорию",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.pack(pady=(0, 10))
        
        list_frame = ctk.CTkFrame(main_container)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        scrollable_frame = ctk.CTkScrollableFrame(
            list_frame,
            height=260
        )
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        def reload_categories():
            # Очистка содержимого
            for child in scrollable_frame.winfo_children():
                child.destroy()
            
            # Получаем ID присвоенных категорий
            assigned_ids = set(get_chat_categories(chat_tg_id))
            if not assigned_ids:
                empty_label = ctk.CTkLabel(
                    scrollable_frame,
                    text="Категории не присвоены",
                    font=ctk.CTkFont(size=12),
                    text_color="gray"
                )
                empty_label.pack(pady=10)
                return

            # Получаем имена категорий и фильтруем только присвоенные
            all_categories = get_all_categories()
            categories = [(cid, name) for cid, name in all_categories if cid in assigned_ids]
            
            for cat_id, cat_name in categories:
                row = ctk.CTkFrame(scrollable_frame)
                row.pack(fill="x", padx=5, pady=4)
                
                name_label = ctk.CTkLabel(
                    row,
                    text=cat_name,
                    font=ctk.CTkFont(size=12),
                    anchor="w"
                )
                name_label.pack(side="left", fill="x", expand=True, padx=(5, 5))
                
                remove_button = ctk.CTkButton(
                    row,
                    text="✕",
                    width=28,
                    height=24,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    fg_color="#8b0000",
                    hover_color="#a00000",
                    command=lambda cid=cat_id: self._on_remove_category(chat_tg_id, cid, reload_categories)
                )
                remove_button.pack(side="right", padx=(5, 5))
        
        reload_categories()
        
        close_button = ctk.CTkButton(
            main_container,
            text="Закрыть",
            width=120,
            command=dialog.destroy
        )
        close_button.pack(pady=(0, 5))

    def _on_remove_category(self, chat_tg_id, category_id, reload_callback):
        """Удаляет категорию из чата и обновляет UI."""
        from db_logic import remove_category_from_chat
        try:
            remove_category_from_chat(chat_tg_id, category_id)
            # Обновляем список в диалоге
            reload_callback()
            # Обновляем основную таблицу
            self.refresh_table()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить категорию: {str(e)}")

    def _get_chat_by_id(self, tg_id: int):
        """
        Возвращает информацию о чате по Telegram ID из кэша self.all_chats.
        Формат: (title, participants_count, categories, chat_type) или None.
        """
        if not getattr(self, "all_chats", None):
            return None
        for chat_tg_id, title, participants_count, categories, chat_type in self.all_chats:
            if chat_tg_id == tg_id:
                return (title, participants_count, categories, chat_type)
        return None

    def _show_export_dialog(self, chat_tg_id: int, chat_title: str, chat_type: str):
        """
        Показывает мини-окошко выбора папки и запуска экспорта чата.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Экспорт чата")
        dialog.geometry("500x220")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            main_container,
            text=f"Экспорт чата:\n{chat_title}",
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="center",
        )
        title_label.pack(pady=(0, 15))

        # Выбор папки
        path_var = ctk.StringVar(value="Не выбрана")

        path_frame = ctk.CTkFrame(main_container)
        path_frame.pack(fill="x", pady=(0, 10))

        path_entry = ctk.CTkEntry(
            path_frame,
            textvariable=path_var,
            state="disabled",
            width=320,
        )
        path_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

        def choose_dir():
            dirname = filedialog.askdirectory()
            if dirname:
                path_var.set(dirname)

        choose_button = ctk.CTkButton(
            path_frame,
            text="Выбрать папку",
            command=choose_dir,
            width=120,
        )
        choose_button.pack(side="left")

        # Кнопки управления
        button_frame = ctk.CTkFrame(main_container)
        button_frame.pack(fill="x", pady=(15, 0))

        def on_start():
            export_dir = path_var.get().strip()
            if not export_dir or export_dir == "Не выбрана":
                messagebox.showerror("Ошибка", "Выберите папку для экспорта")
                return

            dialog.destroy()

            # Запускаем экспорт в отдельном потоке
            thread = threading.Thread(
                target=self._export_chat_thread,
                args=(chat_tg_id, chat_title, chat_type, export_dir),
            )
            thread.daemon = True
            thread.start()

        start_button = ctk.CTkButton(
            button_frame,
            text="Начать экспорт",
            command=on_start,
            width=160,
            fg_color="#0066cc",
            hover_color="#0052a3",
        )
        start_button.pack(side="left", padx=5)

        cancel_button = ctk.CTkButton(
            button_frame,
            text="Отмена",
            command=dialog.destroy,
            width=120,
            fg_color="gray",
            hover_color="darkgray",
        )
        cancel_button.pack(side="left", padx=5)

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
    
    def _export_chat_thread(self, chat_tg_id: int, chat_title: str, chat_type: str, export_dir: str):
        """
        Выполняет экспорт чата в отдельном потоке, чтобы не блокировать UI.
        """
        try:
            # Проверяем наличие API credentials
            if not self.api_id or not self.api_hash:
                self.after(0, lambda: messagebox.showwarning(
                    "Предупреждение",
                    "Сначала подключитесь через кнопку 'Подключиться'"
                ))
                return

            # Инициализируем/используем существующий TelegramManager
            if not self.telegram_manager:
                manager = TelegramManager(self.api_id, self.api_hash)
                self.telegram_manager = manager
            else:
                manager = self.telegram_manager

            # Подключаемся при необходимости
            self.after(0, lambda: self.status_label.configure(
                text=f"Подключение к Telegram для экспорта чата '{chat_title}'..."
            ))
            success, message = manager.connect()
            if not success and message in ["phone", "code", "password"]:
                self.after(0, lambda: messagebox.showwarning(
                    "Требуется авторизация",
                    "Сначала подключитесь через кнопку 'Подключиться'"
                ))
                return
            elif not success:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Ошибка подключения: {message}"
                ))
                self.after(0, lambda: messagebox.showerror(
                    "Ошибка подключения",
                    message
                ))
                return

            self.after(0, lambda: self.status_label.configure(
                text=f"Экспорт чата '{chat_title}'..."
            ))

            settings = getattr(self, "export_settings", None) or self.load_export_settings()

            result = manager.export_chat_history_md(
                chat_id=chat_tg_id,
                chat_title=chat_title,
                base_export_dir=export_dir,
                chat_type=chat_type,
                words_per_file=settings.get("words_per_file", 50000),
                delay_messages_chunk=settings.get("delay_messages_chunk", 1000),
                delay_seconds=settings.get("delay_seconds", 1.0),
            )

            def on_success():
                msgs = result.get("messages_exported", 0)
                files_used = result.get("files_used", 0)
                chat_dir = result.get("chat_dir", export_dir)
                self.status_label.configure(
                    text=(
                        f"Экспорт завершён: сообщений {self._format_number(msgs)}, "
                        f"файлов {self._format_number(files_used)}"
                    )
                )
                messagebox.showinfo(
                    "Экспорт завершён",
                    f"Экспорт чата '{chat_title}' завершён.\n"
                    f"Сообщений: {self._format_number(msgs)}\n"
                    f"Файлов: {self._format_number(files_used)}\n"
                    f"Папка: {chat_dir}"
                )

            self.after(0, on_success)

        except Exception as e:
            err = str(e)

            def on_error():
                self.status_label.configure(text=f"Ошибка экспорта: {err}")
                messagebox.showerror("Ошибка экспорта", err)

            self.after(0, on_error)

    def _show_message_stats_chart(self, chat_tg_id: int, chat_title: str, chat_type: str):
        """
        Показывает диалог с выбором действия: построить график или обновить данные.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("График сообщений")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Центрируем окно
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            main_container,
            text=f"График сообщений:\n{chat_title}",
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="center",
        )
        title_label.pack(pady=(0, 10))

        # Label для статуса прогресса
        status_label = ctk.CTkLabel(
            main_container,
            text="",
            font=ctk.CTkFont(size=12),
            justify="center",
            text_color="gray",
        )
        status_label.pack(pady=(0, 15))

        button_frame = ctk.CTkFrame(main_container)
        button_frame.pack(fill="x", pady=(0, 10))

        def on_build_chart():
            # Проверяем наличие данных, если нет - сначала обновляем
            if not has_message_stats_for_chat(chat_tg_id):
                # Нет данных - сначала обновляем, потом строим график
                # Отключаем кнопки во время обновления
                build_button.configure(state="disabled")
                update_button.configure(state="disabled")
                self._update_message_stats_and_build_chart(chat_tg_id, chat_title, chat_type, dialog, status_label)
            else:
                # Данные есть - просто строим график и закрываем диалог
                dialog.destroy()
                self._build_chart_from_existing_data(chat_tg_id, chat_title)

        def on_update_data():
            # Отключаем кнопки во время обновления
            build_button.configure(state="disabled")
            update_button.configure(state="disabled")
            self._update_message_stats_only(chat_tg_id, chat_title, chat_type, dialog, status_label)

        build_button = ctk.CTkButton(
            button_frame,
            text="Построить график",
            command=on_build_chart,
            width=160,
            fg_color="#0066cc",
            hover_color="#0052a3",
        )
        build_button.pack(side="left", padx=5, expand=True)

        update_button = ctk.CTkButton(
            button_frame,
            text="Обновить данные",
            command=on_update_data,
            width=160,
            fg_color="#0066cc",
            hover_color="#0052a3",
        )
        update_button.pack(side="left", padx=5, expand=True)

        # Сохраняем ссылки на кнопки для последующего включения
        dialog.build_button = build_button
        dialog.update_button = update_button

    def _update_message_stats_only(self, chat_tg_id: int, chat_title: str, chat_type: str, dialog, status_label):
        """
        Обновляет данные в таблице message_stats для чата (без построения графика).
        """
        thread = threading.Thread(
            target=self._update_message_stats_thread,
            args=(chat_tg_id, chat_title, chat_type, dialog, status_label, False),
        )
        thread.daemon = True
        thread.start()

    def _update_message_stats_and_build_chart(self, chat_tg_id: int, chat_title: str, chat_type: str, dialog, status_label):
        """
        Обновляет данные в таблице message_stats и строит график.
        """
        thread = threading.Thread(
            target=self._update_message_stats_thread,
            args=(chat_tg_id, chat_title, chat_type, dialog, status_label, True),
        )
        thread.daemon = True
        thread.start()

    def _update_message_stats_thread(
        self,
        chat_tg_id: int,
        chat_title: str,
        chat_type: str,
        dialog,
        status_label,
        build_chart_after: bool,
    ):
        """
        Фоновая логика: обновляет таблицу message_stats для чата.
        Если build_chart_after=True, после обновления строит график.
        """
        try:
            def update_status(text: str):
                """Обновляет текст статуса в диалоге."""
                self.after(0, lambda: status_label.configure(text=text))

            def enable_buttons():
                """Включает кнопки обратно."""
                self.after(0, lambda: dialog.build_button.configure(state="normal"))
                self.after(0, lambda: dialog.update_button.configure(state="normal"))

            # Проверяем наличие API credentials
            if not self.api_id or not self.api_hash:
                enable_buttons()
                self.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Предупреждение",
                        "Сначала подключитесь через кнопку 'Подключиться'",
                    ),
                )
                return

            # Инициализируем/используем существующий TelegramManager
            if not self.telegram_manager:
                manager = TelegramManager(self.api_id, self.api_hash)
                self.telegram_manager = manager
            else:
                manager = self.telegram_manager

            # Подключаемся при необходимости
            update_status("Подключение к Telegram...")
            self.after(0, lambda: self.status_label.configure(
                text=f"Подключение к Telegram для получения статистики чата '{chat_title}'..."
            ))
            success, message = manager.connect()
            if not success and message in ["phone", "code", "password"]:
                enable_buttons()
                update_status("")
                self.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Требуется авторизация",
                        "Сначала подключитесь через кнопку 'Подключиться'",
                    ),
                )
                return
            elif not success:
                enable_buttons()
                update_status(f"Ошибка подключения: {message}")
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Ошибка подключения",
                        message,
                    ),
                )
                return

            # Забираем все сообщения с самого начала истории
            update_status("Пожалуйста, подождите.\nДанные загружаются...")
            from tg_logic import TelegramManager as _TM
            try:
                all_messages = manager.get_chat_messages_for_stats(
                    chat_id=chat_tg_id,
                    chat_type=chat_type,
                    min_message_id=0,  # все сообщения
                )
            except Exception as e:
                err = str(e)
                enable_buttons()
                update_status(f"Ошибка получения сообщений: {err}")
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Ошибка получения сообщений",
                        err,
                    ),
                )
                return

            # Полностью пересобираем таблицу message_stats для этого чата
            update_status("Сохранение данных в таблицу...")
            to_store = [
                (msg["message_id"], msg["date_time"], msg.get("text", ""))
                for msg in all_messages
            ]
            replace_message_stats_for_chat(chat_tg_id, to_store)

            # Получаем агрегированную статистику по дням
            daily_counts = get_daily_message_counts(chat_tg_id)

            # Уведомление о завершении обновления
            def show_loaded_info():
                total_msgs = len(to_store)
                total_days = len(daily_counts)
                status_text = (
                    f"Данные обновлены: "
                    f"сообщений {self._format_number(total_msgs)}, "
                    f"дней {self._format_number(total_days)}"
                )
                status_label.configure(text=status_text)
                self.status_label.configure(
                    text=(
                        f"Статистика сообщений обновлена: "
                        f"сообщений {self._format_number(total_msgs)}, "
                        f"дней в выборке {self._format_number(total_days)}"
                    )
                )
                enable_buttons()

            self.after(0, show_loaded_info)

            # Если нужно построить график - строим и закрываем диалог
            if build_chart_after:
                self.after(
                    0,
                    lambda: dialog.destroy()
                )
                self.after(
                    0,
                    lambda: self._open_message_stats_chart_window(
                        chat_tg_id,
                        chat_title,
                        daily_counts,
                    ),
                )

        except Exception as e:
            err = str(e)

            def on_error():
                enable_buttons()
                status_label.configure(text=f"Ошибка: {err}")
                self.status_label.configure(text=f"Ошибка обновления данных: {err}")
                messagebox.showerror("Ошибка обновления данных", err)

            self.after(0, on_error)

    def _build_chart_from_existing_data(self, chat_tg_id: int, chat_title: str):
        """
        Строит график из существующих данных в таблице message_stats.
        """
        try:
            daily_counts = get_daily_message_counts(chat_tg_id)
            if not daily_counts:
                messagebox.showinfo(
                    "Нет данных",
                    "Для этого чата нет данных о сообщениях.\nИспользуйте кнопку 'Обновить данные' для загрузки.",
                )
                return
            self._open_message_stats_chart_window(chat_tg_id, chat_title, daily_counts)
        except Exception as e:
            messagebox.showerror(
                "Ошибка построения графика",
                f"Не удалось построить график: {str(e)}",
            )

    def _open_message_stats_chart_window(
        self,
        chat_tg_id: int,
        chat_title: str,
        daily_counts,
    ):
        """
        Открывает график количества сообщений по датам с помощью PyQtGraph.
        """
        if not daily_counts:
            messagebox.showinfo(
                "Нет данных",
                "Для этого чата пока нет данных о сообщениях.",
            )
            return

        # Берём настройки графика (из кэша или перечитываем с диска)
        chart_settings = getattr(self, "chart_settings", None) or self.load_chart_settings()

        # Преобразуем входные данные в словарь дата -> кол-во сообщений
        from datetime import datetime as _dt, timedelta as _td

        date_to_count = {}
        for d_str, cnt in daily_counts:
            try:
                d = _dt.strptime(d_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            date_to_count[d] = int(cnt)

        if not date_to_count:
            messagebox.showinfo(
                "Нет данных",
                "Не удалось подготовить данные для графика.",
            )
            return

        # Строим полный диапазон дней от первого сообщения до последнего
        first_day = min(date_to_count.keys())
        last_day = max(date_to_count.keys())

        all_dates = []
        all_counts = []
        current = first_day
        while current <= last_day:
            all_dates.append(current)
            all_counts.append(date_to_count.get(current, 0))
            current += _td(days=1)

        # Готовим данные для столбчатого графика PyQtGraph:
        # x — индекс дня в диапазоне, y — количество сообщений
        x_values = list(range(len(all_dates)))
        y_values = all_counts

        try:
            # Создаём/переиспользуем приложение Qt
            app = QtWidgets.QApplication.instance()
            if app is None:
                app = QtWidgets.QApplication([])

            # Создаём главное окно (QMainWindow) для графика
            main_window = QtWidgets.QMainWindow()
            main_window.setWindowTitle(f"График сообщений: {chat_title} ({chat_tg_id})")
            
            # Создаём центральный виджет с графиком
            central_widget = pg.GraphicsLayoutWidget()
            main_window.setCentralWidget(central_widget)
            
            # Устанавливаем размер окна на весь экран
            screen = app.primaryScreen().geometry()
            main_window.resize(screen.width(), screen.height())
            
            plot = central_widget.addPlot()
            plot.setLabel("bottom", "Дата")
            plot.setLabel("left", "Количество сообщений")

            # Столбчатый график
            bar_color = chart_settings.get("bar_color", "#1f77b4")
            bar_item = pg.BarGraphItem(
                x=x_values,
                height=y_values,
                width=0.8,
                brush=bar_color,
            )
            plot.addItem(bar_item)

            # Подписи по оси X: каждый день от первого до последнего сообщения
            # Ограничиваем количество подписей для читаемости (показываем каждую N-ю дату)
            num_ticks = min(20, len(x_values))  # Максимум 20 подписей
            if num_ticks > 0 and len(x_values) > 1:
                step = max(1, len(x_values) // num_ticks)
                ticks = [(i, all_dates[i].strftime("%Y-%m-%d")) for i in range(0, len(x_values), step)]
            else:
                ticks = [(i, all_dates[i].strftime("%Y-%m-%d")) for i in x_values]
            
            axis = plot.getAxis("bottom")
            axis.setTicks([ticks])
            axis.setStyle(tickFont=QtGui.QFont("Sans Serif", 8))

            # Сохраняем ссылку на окно, чтобы оно не удалилось сборщиком мусора
            if not hasattr(self, '_chart_windows'):
                self._chart_windows = []
            self._chart_windows.append(main_window)

            # Открываем окно в полноэкранном режиме
            main_window.show()
            main_window.showMaximized()
            
            # Принудительно поднимаем окно на передний план и даём ему фокус
            main_window.setWindowState(main_window.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
            main_window.raise_()
            main_window.activateWindow()
            main_window.setFocus()
            
            # Принудительно обрабатываем события, чтобы окно точно появилось на переднем плане
            app.processEvents()
            
            # Запускаем обработку событий Qt в отдельном потоке
            def run_qt_event_loop():
                import time
                while main_window.isVisible():
                    app.processEvents()
                    time.sleep(0.01)
            
            import threading
            qt_thread = threading.Thread(target=run_qt_event_loop, daemon=True)
            qt_thread.start()
            
            # Дополнительно поднимаем окно на передний план после небольшой задержки
            def bring_to_front():
                main_window.setWindowState(main_window.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
                main_window.raise_()
                main_window.activateWindow()
                main_window.setFocus()
                app.processEvents()
            
            self.after(100, bring_to_front)
            self.after(300, bring_to_front)  # Дополнительная попытка через 300мс
            
        except Exception as e:
            messagebox.showerror(
                "Ошибка открытия графика",
                f"Не удалось открыть график: {str(e)}",
            )

def main():
    """Точка входа в приложение."""
    app = TelegramChatsApp()
    app.mainloop()


if __name__ == "__main__":
    main()

