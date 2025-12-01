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
    search_available_categories_for_chat,
    get_last_message_id_for_chat,
    append_message_stats,
    replace_message_stats_for_chat,
    has_message_stats_for_chat,
    get_daily_message_counts,
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
    'search_available_categories_for_chat',
    'get_last_message_id_for_chat',
    'append_message_stats',
    'replace_message_stats_for_chat',
    'has_message_stats_for_chat',
    'get_daily_message_counts',
]

