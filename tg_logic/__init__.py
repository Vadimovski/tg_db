"""
Модуль для работы с Telegram API.
"""
from .telegram_logic import (
    TelegramManager,
    save_api_credentials,
    load_api_credentials,
    get_api_credentials,
    authenticate_and_get_chats
)

__all__ = [
    'TelegramManager',
    'save_api_credentials',
    'load_api_credentials',
    'get_api_credentials',
    'authenticate_and_get_chats'
]

