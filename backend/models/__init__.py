# backend/models/__init__.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Models module for the application.
Imports all model classes and re-exports them for convenient imports elsewhere.
"""

# Schemas for request/response models
from models.schemas.user import User, UserCreate
from models.schemas.news import (
    NewsItem as News,  # Alias NewsItem as News
    NewsItemCreate as NewsCreate,  # Alias NewsItemCreate as NewsCreate
    NewsItemUpdate as NewsUpdate,  # Alias NewsItemUpdate as NewsUpdate
    NewsCategory,
    NewsCategoryCreate,
    NewsCategoryUpdate,  # Keep NewsCategoryUpdate if it exists elsewhere or might be added
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    FetchSourceRequest,
    FetchSourceBatchRequest,
    FetchUrlRequest,
    AnalyzeRequest,
    AnalyzeContentRequest,
    AnalysisResult,
    UpdateAnalysisRequest,
)
from models.schemas.api_key import ApiKey, ApiKeyCreate
from models.schemas.settings import (
    UserPreference,
    UserPreferenceBase,
    UserPreferenceUpdate,
)
from models.schemas.chat import (
    Chat,
    ChatCreate,
    Message,
    MessageCreate,
    ChatAnswer,
    Question,
)

# Import UserInDB if needed internally, but don't export typically
from models.schemas.user import UserInDB

# Re-export models for convenient imports elsewhere
__all__ = [
    # User related
    "User",
    "UserCreate",
    # News related
    "News",
    "NewsCreate",
    "NewsUpdate",
    "NewsCategory",
    "NewsCategoryCreate",
    "NewsCategoryUpdate",
    "NewsSource",
    "NewsSourceCreate",
    "NewsSourceUpdate",
    "FetchSourceRequest",
    "FetchSourceBatchRequest",
    "FetchUrlRequest",
    "AnalyzeRequest",
    "AnalyzeContentRequest",
    "AnalysisResult",
    "UpdateAnalysisRequest",
    # API Key related
    "ApiKey",
    "ApiKeyCreate",
    # Settings related
    "UserPreference",
    "UserPreferenceBase",
    "UserPreferenceUpdate",
    # Chat related
    "Chat",
    "ChatCreate",
    "Message",
    "MessageCreate",
    "ChatAnswer",
    "Question",
]
