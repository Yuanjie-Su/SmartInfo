# backend/models/__init__.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Models package: Exports Pydantic schemas for data validation and serialization.
"""

# Import schemas from their specific files within the schemas directory
from .schemas.api_key import ApiKeyBase, ApiKeyCreate, ApiKey
from .schemas.chat import (
    MessageBase,
    MessageCreate,
    Message,
    ChatBase,
    ChatCreate,
    Chat,
    ChatAnswer,
    Question,
)
from .schemas.news import (
    NewsSourceBase,
    NewsSourceCreate,
    NewsSourceUpdate,
    NewsSource,
    NewsCategoryBase,
    NewsCategoryCreate,
    NewsCategoryUpdate,
    NewsCategory,
    NewsItemBase,
    NewsItemCreate,
    NewsItemUpdate,
    NewsItem,
    FetchSourceRequest,
    FetchUrlRequest,
    AnalyzeRequest,
    AnalyzeContentRequest,
    AnalysisResult,
    UpdateAnalysisRequest,
)
from .schemas.settings import (
    SystemConfigBase,
    SystemConfig,
    SystemConfigUpdate,
)


__all__ = [
    # API Key Schemas
    "ApiKeyBase",
    "ApiKeyCreate",
    "ApiKey",
    # Chat Schemas
    "MessageBase",
    "MessageCreate",
    "Message",
    "ChatBase",
    "ChatCreate",
    "Chat",
    "ChatAnswer",
    "Question",
    # News Schemas
    "NewsSourceBase",
    "NewsSourceCreate",
    "NewsSourceUpdate",
    "NewsSource",
    "NewsCategoryBase",
    "NewsCategoryCreate",
    "NewsCategoryUpdate",
    "NewsCategory",
    "NewsItemBase",
    "NewsItemCreate",
    "NewsItemUpdate",
    "NewsItem",
    "FetchSourceRequest",
    "FetchUrlRequest",
    "AnalyzeRequest",
    "AnalyzeContentRequest",
    "AnalysisResult",
    "UpdateAnalysisRequest",
    # Settings Schemas
    "SystemConfigBase",
    "SystemConfig",
    "SystemConfigUpdate",
]
