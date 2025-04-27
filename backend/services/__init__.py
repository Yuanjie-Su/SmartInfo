# backend/services/__init__.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Service Layer Package.

Contains classes encapsulating the application's business logic,
coordinating interactions between the API layer, data repositories,
and core components like the LLM client pool.
"""

from .chat_service import ChatService
from .news_service import NewsService
from .setting_service import SettingService

__all__ = [
    "ChatService",
    "NewsService",
    "SettingService",
]
