#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Centralized dependencies for FastAPI route functions in API v1.
Provides dependency injection for database connections, repositories, services, and the LLM pool.
"""

import aiosqlite
import logging
from fastapi import Depends, HTTPException, status
from typing import Optional

# Import components using absolute backend package path
from backend.config import config
from backend.db.connection import get_db_connection
from backend.db.repositories import (
    ApiKeyRepository,
    ChatRepository,
    MessageRepository,
    NewsRepository,
    NewsCategoryRepository,
    NewsSourceRepository,
    SystemConfigRepository,
)
from backend.services import (
    ChatService,
    NewsService,
    SettingService,
)

# Import LLM Pool from its new location in core
from backend.core.llm import LLMClientPool

logger = logging.getLogger(__name__)

# Global instance for the LLM Pool (managed by lifespan in main.py)
# This variable will be set by the lifespan event handlers in main.py
_global_llm_pool: Optional[LLMClientPool] = None


def set_global_llm_pool(pool: LLMClientPool):
    """
    Sets the global LLM pool instance. Called from main.py lifespan startup.
    """
    global _global_llm_pool
    if _global_llm_pool is not None:
        logger.warning(
            "Global LLM pool is being reset. This should ideally happen only once."
        )
    _global_llm_pool = pool
    logger.info("Global LLM pool has been set.")


async def get_db_connection_dependency() -> aiosqlite.Connection:
    """
    Dependency function that provides the application's SQLite database connection.
    Relies on the connection manager initialized in main.py.
    """
    try:
        return await get_db_connection()
    except RuntimeError as e:
        # This error occurs if the DB manager wasn't initialized (lifespan issue)
        logger.critical(f"Database connection dependency error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )


# --- Repository Dependencies ---


async def get_api_key_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> ApiKeyRepository:
    """Provides an instance of ApiKeyRepository."""
    return ApiKeyRepository(db)


async def get_chat_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> ChatRepository:
    """Provides an instance of ChatRepository."""
    return ChatRepository(db)


async def get_message_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> MessageRepository:
    """Provides an instance of MessageRepository."""
    return MessageRepository(db)


async def get_news_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> NewsRepository:
    """Provides an instance of NewsRepository."""
    return NewsRepository(db)


async def get_news_category_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> NewsCategoryRepository:
    """Provides an instance of NewsCategoryRepository."""
    return NewsCategoryRepository(db)


async def get_news_source_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> NewsSourceRepository:
    """Provides an instance of NewsSourceRepository."""
    return NewsSourceRepository(db)


async def get_system_config_repository(
    db: aiosqlite.Connection = Depends(get_db_connection_dependency),
) -> SystemConfigRepository:
    """Provides an instance of SystemConfigRepository."""
    return SystemConfigRepository(db)


# --- Service Dependencies ---


def get_llm_pool_dependency() -> LLMClientPool:
    """
    Dependency that provides the global LLM pool instance.
    Raises an error if the pool has not been initialized by the application lifespan.
    """
    if _global_llm_pool is None:
        logger.error(
            "LLM Client Pool dependency requested but pool is not initialized."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available.",
        )
    return _global_llm_pool


async def get_chat_service(
    chat_repo: ChatRepository = Depends(get_chat_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    llm_pool: LLMClientPool = Depends(get_llm_pool_dependency),
) -> ChatService:
    """Provides an instance of ChatService with its dependencies."""
    service = ChatService(chat_repo=chat_repo, message_repo=message_repo)
    service.set_llm_pool(llm_pool)  # Inject LLM pool after service creation
    return service


async def get_news_service(
    news_repo: NewsRepository = Depends(get_news_repository),
    source_repo: NewsSourceRepository = Depends(get_news_source_repository),
    category_repo: NewsCategoryRepository = Depends(get_news_category_repository),
    llm_pool: LLMClientPool = Depends(get_llm_pool_dependency),
) -> NewsService:
    """Provides an instance of NewsService with its dependencies."""
    service = NewsService(
        news_repo=news_repo, source_repo=source_repo, category_repo=category_repo
    )
    service.set_llm_pool(llm_pool)  # Inject LLM pool after service creation
    return service


async def get_setting_service(
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
    system_config_repo: SystemConfigRepository = Depends(get_system_config_repository),
) -> SettingService:
    """Provides an instance of SettingService with its dependencies."""
    # Requires the global 'config' instance from backend.config
    return SettingService(
        config=config,
        api_key_repo=api_key_repo,
        system_config_repo=system_config_repo,
    )
