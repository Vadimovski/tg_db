"""
Модуль для работы с Telegram API через библиотеку Telethon.
Обеспечивает аутентификацию и получение списка чатов/каналов.
"""
import os
import json
import asyncio
import datetime
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, Message, PeerChannel, PeerChat
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

    def export_chat_history_md(
        self,
        chat_id: int,
        chat_title: str,
        base_export_dir: str,
        chat_type: Optional[str] = None,
        words_per_file: int = 50000,
        delay_messages_chunk: int = 1000,
        delay_seconds: float = 1.0,
    ) -> Dict[str, any]:
        """
        Экспортирует историю чата в markdown-файлы с разбиением по words_per_file слов.

        Прогресс экспорта сохраняется в файле export_index.json внутри папки конкретного чата,
        чтобы при повторном запуске дописывать только новые сообщения.

        Формат файла:
        - Заголовок с названием чата
        - Для каждого сообщения:
            ### YYYY-MM-DD HH:MM:SS — Автор
            [id: MESSAGE_ID]

            Текст сообщения

            ---
        """
        import re

        # Устанавливаем event loop
        asyncio.set_event_loop(self.loop)

        def safe_chat_folder_name(title: str) -> str:
            """Безопасное имя папки/файла для чата."""
            title = title or "chat"
            # Убираем переводы строк и лишние пробелы
            title = " ".join(title.split())
            # Заменяем запрещённые в имени файла символы
            title = re.sub(r'[\\/:*?"<>|]', "_", title)
            # Ограничиваем длину, чтобы не упираться в лимиты файловой системы
            return title[:80] if len(title) > 80 else title

        # Базовая директория экспорта и директория конкретного чата
        base_path = Path(base_export_dir)
        chat_folder_name = f"{safe_chat_folder_name(chat_title)}_{chat_id}"
        chat_dir = base_path / chat_folder_name
        chat_dir.mkdir(parents=True, exist_ok=True)

        index_path = chat_dir / "export_index.json"

        # Инициализация прогресса
        last_message_id: Optional[int] = None
        file_index: int = 1
        current_words: int = 0

        if index_path.exists():
            try:
                with index_path.open("r", encoding="utf-8") as f:
                    idx = json.load(f)
                last_message_id = idx.get("last_message_id")
                file_index = int(idx.get("last_file_index", 1))
                current_words = int(idx.get("current_file_word_count", 0))
            except Exception:
                # Если индекс повреждён, начинаем с нуля
                last_message_id = None
                file_index = 1
                current_words = 0

        def make_file_path(i: int) -> Path:
            filename = f"{safe_chat_folder_name(chat_title)}_chatexport_{i:02d}.md"
            return chat_dir / filename

        file_path = make_file_path(file_index)
        file_exists = file_path.exists()
        file = file_path.open("a", encoding="utf-8")

        # Если файл новый/пустой, пишем заголовок с названием чата
        if not file_exists or file_path.stat().st_size == 0:
            file.write(f"# {chat_title}\n\n")

        def save_index() -> None:
            data = {
                "chat_id": chat_id,
                "chat_title": chat_title,
                "last_message_id": last_message_id,
                "last_file_index": file_index,
                "current_file_word_count": current_words,
                "words_per_file": words_per_file,
                "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
            }
            try:
                with index_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                # Ошибку записи индекса не считаем фатальной для экспорта
                pass

        async def _export() -> Dict[str, any]:
            nonlocal last_message_id, file_index, current_words, file

            # Убеждаемся, что клиент подключён и авторизован
            if not self.client.is_connected():
                await self.client.connect()
            if not await self.client.is_user_authorized():
                raise RuntimeError("Telegram client is not authorized")

            # Явно резолвим сущность чата/канала, чтобы избежать ошибок
            # вида "Could not find the input entity for PeerUser(...)"
            peer = chat_id
            try:
                if chat_type == "channel":
                    peer = PeerChannel(chat_id)
                elif chat_type == "chat":
                    peer = PeerChat(chat_id)
            except Exception:
                peer = chat_id

            try:
                entity = await self.client.get_entity(peer)
            except Exception as e:
                raise RuntimeError(f"Не удалось получить сущность чата {chat_id}: {e}")

            # Итерируемся по сообщениям от самых старых к новым
            messages_iter = self.client.iter_messages(
                entity=entity,
                reverse=True,
                min_id=(last_message_id or 0),
            )

            messages_processed = 0

            async for msg in messages_iter:
                if not isinstance(msg, Message):
                    continue

                # Нас интересуют только текстовые сообщения
                text = getattr(msg, "message", None)
                if not text:
                    continue

                words = text.split()
                msg_words = len(words)
                if msg_words == 0:
                    continue

                # Проверяем лимит слов: если текущее сообщение не влезает,
                # переносим его целиком в новый файл
                if current_words > 0 and current_words + msg_words > words_per_file:
                    file.close()

                    file_index += 1
                    current_words = 0

                    new_path = make_file_path(file_index)
                    file = new_path.open("a", encoding="utf-8")
                    file.write(f"# {chat_title}\n\n")

                # Подготовка метаданных сообщения
                dt = msg.date.astimezone() if msg.date else None
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

                sender_name = ""
                try:
                    if msg.sender:
                        first = getattr(msg.sender, "first_name", "") or ""
                        last = getattr(msg.sender, "last_name", "") or ""
                        username = getattr(msg.sender, "username", "") or ""
                        if first or last:
                            sender_name = (first + " " + last).strip()
                        elif username:
                            sender_name = f"@{username}"
                except Exception:
                    sender_name = ""

                header_line = f"### {dt_str}"
                if sender_name:
                    header_line += f" — {sender_name}"

                file.write(header_line + "\n")
                file.write(f"[id: {msg.id}]\n\n")
                file.write(text.strip() + "\n\n")
                file.write("---\n\n")

                current_words += msg_words
                last_message_id = msg.id
                messages_processed += 1

                # Периодически сохраняем прогресс
                if messages_processed % 50 == 0:
                    save_index()

                # Задержка для снижения нагрузки на Telegram
                if (
                    delay_messages_chunk > 0
                    and messages_processed % delay_messages_chunk == 0
                    and delay_seconds > 0
                ):
                    await asyncio.sleep(delay_seconds)

            # Завершение экспорта: закрываем файл и сохраняем индекс
            file.close()
            save_index()

            return {
                "messages_exported": messages_processed,
                "files_used": file_index,
                "chat_dir": str(chat_dir),
            }

        try:
            result = self.loop.run_until_complete(_export())
        finally:
            try:
                file.close()
            except Exception:
                pass

        return result

    def get_chat_messages_for_stats(
        self,
        chat_id: int,
        chat_type: Optional[str] = None,
        min_message_id: int = 0,
    ) -> List[Dict[str, any]]:
        """
        Возвращает список сообщений для построения статистики.

        Сообщения выбираются от самого старого к новому, начиная с message_id > min_message_id.
        Для каждого сообщения возвращаются:
        - message_id: ID сообщения
        - date_time: время сообщения в ISO-формате (локальное время)
        - text: текст сообщения (может быть пустой строкой)
        """
        from telethon.tl.types import PeerChannel, PeerChat

        asyncio.set_event_loop(self.loop)

        async def _collect() -> List[Dict[str, any]]:
            result: List[Dict[str, any]] = []

            # Убеждаемся, что клиент подключён и авторизован
            if not self.client.is_connected():
                await self.client.connect()
            if not await self.client.is_user_authorized():
                raise RuntimeError("Telegram client is not authorized")

            # Определяем peer для чата
            peer = chat_id
            try:
                if chat_type == "channel":
                    peer = PeerChannel(chat_id)
                elif chat_type == "chat":
                    peer = PeerChat(chat_id)
            except Exception:
                peer = chat_id

            try:
                entity = await self.client.get_entity(peer)
            except Exception as e:
                raise RuntimeError(f"Не удалось получить сущность чата {chat_id}: {e}")

            messages_iter = self.client.iter_messages(
                entity=entity,
                reverse=True,
                min_id=max(0, int(min_message_id)),
            )

            async for msg in messages_iter:
                if not isinstance(msg, Message):
                    continue
                dt = msg.date.astimezone() if msg.date else None
                dt_iso = dt.isoformat() if dt else ""
                text = getattr(msg, "message", "") or ""
                result.append(
                    {
                        "message_id": int(msg.id),
                        "date_time": dt_iso,
                        "text": text,
                    }
                )

            return result

        msgs = self.loop.run_until_complete(_collect())
        return msgs
    
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

