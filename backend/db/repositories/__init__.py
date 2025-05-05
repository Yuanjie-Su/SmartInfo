"""
Repository classes for database operations
"""

from db.repositories.news_repository import NewsRepository
from db.repositories.news_source_repository import NewsSourceRepository
from db.repositories.news_category_repository import NewsCategoryRepository
from db.repositories.api_key_repository import ApiKeyRepository
from db.repositories.system_config_repository import SystemConfigRepository
from db.repositories.chat_repository import ChatRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.user_repository import UserRepository

__all__ = [
    "NewsRepository",
    "NewsSourceRepository",
    "NewsCategoryRepository",
    "ApiKeyRepository",
    "SystemConfigRepository",
    "ChatRepository",
    "MessageRepository",
    "UserRepository",
]
