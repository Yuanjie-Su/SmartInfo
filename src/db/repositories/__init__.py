#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repositories Package
Exports all repository classes for easy access.
"""

from .base_repository import BaseRepository
from .news_category_repository import NewsCategoryRepository
from .news_source_repository import NewsSourceRepository
from .news_repository import NewsRepository
from .api_key_repository import ApiKeyRepository
from .system_config_repository import SystemConfigRepository
from .chat_repository import ChatRepository
from .message_repository import MessageRepository

# Define what is accessible when using 'from src.db.repositories import *'
# Although explicit imports are generally preferred.
__all__ = [
    "BaseRepository",
    "NewsCategoryRepository",
    "NewsSourceRepository",
    "NewsRepository",
    "ApiKeyRepository",
    "SystemConfigRepository",
    "ChatRepository",
    "MessageRepository",
] 