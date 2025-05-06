#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Centralized dependencies for FastAPI route functions in API v1.
Provides dependency injection for database connections, repositories, services, and the LLM pool.
"""

import aiosqlite
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer  # Import OAuth2PasswordBearer
from typing import Optional, Annotated  # Import Annotated
import asyncpg

# Import components using absolute backend package path
from config import config
from db.connection import get_db_connection_context
from db.repositories import (
    ApiKeyRepository,
    ChatRepository,
    MessageRepository,
    NewsRepository,
    NewsCategoryRepository,
    NewsSourceRepository,
    UserPreferenceRepository,
    UserRepository,  # Import UserRepository
)
from models import User  # Import User model
from services import (
    ChatService,
    NewsService,
    SettingService,
    AuthService,
)

# Import LLM Pool from its new location in core
# Import WebSocket manager
from core.ws_manager import ws_manager

# Import security functions
from core.security import (
    decode_access_token,
    ALGORITHM,
    SECRET_KEY,
)  # Need decode_access_token

logger = logging.getLogger(__name__)

# OAuth2 Scheme
# The tokenUrl should point to the login endpoint created in auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_ws_manager():
    """
    Dependency that provides the global WebSocket manager instance.

    Returns:
        The singleton ws_manager instance
    """
    return ws_manager


async def get_db_connection_context_dependency():
    """
    Dependency function that provides the database connection context manager.
    Relies on the connection manager initialized in main.py.
    """
    try:
        # get_db_connection_context is already an async context manager
        return get_db_connection_context()
    except RuntimeError as e:
        # This error occurs if the DB manager wasn't initialized (lifespan issue)
        logger.critical(f"Database connection dependency error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )


# --- Repository Dependencies ---


async def get_api_key_repository() -> ApiKeyRepository:
    """Provides an instance of ApiKeyRepository."""
    return ApiKeyRepository()


async def get_chat_repository() -> ChatRepository:
    """Provides an instance of ChatRepository."""
    return ChatRepository()


async def get_message_repository() -> MessageRepository:
    """Provides an instance of MessageRepository."""
    return MessageRepository()


async def get_news_repository() -> NewsRepository:
    """Provides an instance of NewsRepository."""
    return NewsRepository()


async def get_news_category_repository() -> NewsCategoryRepository:
    """Provides an instance of NewsCategoryRepository."""
    return NewsCategoryRepository()


async def get_news_source_repository() -> NewsSourceRepository:
    """Provides an instance of NewsSourceRepository."""
    return NewsSourceRepository()


async def get_user_preference_repository() -> UserPreferenceRepository:
    """Provides an instance of UserPreferenceRepository."""
    return UserPreferenceRepository()


# --- Service Dependencies ---


async def get_chat_service(
    chat_repo: ChatRepository = Depends(get_chat_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
) -> ChatService:
    """Provides an instance of ChatService with its dependencies."""
    service = ChatService(
        chat_repo=chat_repo, message_repo=message_repo, api_key_repo=api_key_repo
    )
    return service


async def get_news_service(
    news_repo: NewsRepository = Depends(get_news_repository),
    source_repo: NewsSourceRepository = Depends(get_news_source_repository),
    category_repo: NewsCategoryRepository = Depends(get_news_category_repository),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
    ws_manager=Depends(get_ws_manager),
) -> NewsService:
    """Provides an instance of NewsService with its dependencies."""
    service = NewsService(
        news_repo=news_repo,
        source_repo=source_repo,
        category_repo=category_repo,
        api_key_repo=api_key_repo,
    )
    return service


async def get_setting_service(
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
    user_preference_repo: UserPreferenceRepository = Depends(
        get_user_preference_repository
    ),
) -> SettingService:
    """Provides an instance of SettingService with its dependencies."""
    return SettingService(
        api_key_repo=api_key_repo, user_preference_repo=user_preference_repo
    )


# --- Authentication Dependency ---


async def get_user_repository() -> UserRepository:
    """Provides an instance of UserRepository with a database connection."""
    # Using the repository pattern already established where repositories
    # handle connection acquisition internally
    return UserRepository()


async def get_current_active_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """
    Dependency to get the current active user from the JWT token.

    Validates the token, decodes it, retrieves the user ID, and fetches
    the user from the database. Raises HTTPException 401 if validation fails.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        # This handles decode errors (invalid signature, expired, etc.)
        raise credentials_exception

    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        # Handle cases where 'sub' is not a valid integer string
        raise credentials_exception

    user = await user_repo.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    # Here you could add checks for user status (e.g., is_active) if needed
    # if not user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")

    return user


async def get_auth_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    """Provides an instance of AuthService with its dependencies."""
    return AuthService(user_repo=user_repo)
