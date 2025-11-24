"""
Модуль для работы с базой данных.
"""
from .database import (
    init_database,
    save_chats,
    get_all_chats,
    get_chats_for_display,
    create_category,
    get_all_categories,
    search_categories,
    get_chat_categories,
    add_category_to_chat,
    remove_category_from_chat,
    get_available_categories_for_chat,
    search_available_categories_for_chat
)

__all__ = [
    'init_database',
    'save_chats',
    'get_all_chats',
    'get_chats_for_display',
    'create_category',
    'get_all_categories',
    'search_categories',
    'get_chat_categories',
    'add_category_to_chat',
    'remove_category_from_chat',
    'get_available_categories_for_chat',
    'search_available_categories_for_chat'
]

