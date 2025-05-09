# File: /home/cator/project/SmartInfo/backend/db/connection.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module provides a connection manager for the database.
It handles database connection initialization and cleanup, supporting
both connection pool and single connection modes.
"""

import os
import logging
import asyncpg
import atexit
from threading import Lock
from typing import Optional, Union, AsyncIterator, TYPE_CHECKING
from contextlib import asynccontextmanager, AbstractAsyncContextManager

# Import using backend package path
from config import config  # Import the config instance
from db.schema_constants import (
    Users,
    NewsCategory,
    NewsSource,
    News,
    ApiConfig,
    UserPreferences,
    Chats,
    Messages,
    FetchHistory,
)

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    _instance: Optional["DatabaseConnectionManager"] = None
    _lock = Lock()
    _db_resource: Optional[Union[asyncpg.Pool, asyncpg.Connection]] = None
    _connection_mode: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info("Creating new DatabaseConnectionManager instance.")
                    cls._instance = super(DatabaseConnectionManager, cls).__new__(cls)
                    cls._instance._db_resource = None
                    cls._instance._connection_mode = None
        return cls._instance

    async def _initialize(
        self, db_connection_mode: str = "pool", min_size: int = 2, max_size: int = 2
    ):
        """
        Initialize database connection resource (pool or single connection).

        Args:
            db_connection_mode: str = "pool" or "single"
            min_size: int = 2
            max_size: int = 2

        Returns:
            None
        """
        if self._db_resource is not None:
            logger.warning("Database resource already initialized.")
            return

        self._connection_mode = db_connection_mode
        logger.info(f"Database connection mode: {self._connection_mode}")

        try:
            # Get connection details from config properties
            db_user = config.db_user
            db_password = config.db_password
            db_name = config.db_name
            db_host = config.db_host
            db_port = config.db_port  # Already an int from property

            # Validation is now done in config.__init__, but double-check here just in case
            if not all([db_user, db_password, db_name]):
                # This should theoretically not be reached if config validation works
                raise ValueError(
                    "Missing required database configuration. Check config initialization."
                )

            if self._connection_mode == "pool":
                logger.info(
                    f"Initializing database connection pool to: postgresql://{db_user}:***@{db_host}:{db_port}/{db_name}"
                )
                self._db_resource = await asyncpg.create_pool(
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    host=db_host,
                    port=db_port,
                    min_size=min_size,
                    max_size=max_size,
                )
                # Create tables using a connection from the pool
                await self._create_tables(self._db_resource)
                logger.info("Database connection pool initialized successfully.")

            elif self._connection_mode == "single":
                logger.info(
                    f"Initializing single database connection to: postgresql://{db_user}:***@{db_host}:{db_port}/{db_name}"
                )
                self._db_resource = await asyncpg.connect(
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    host=db_host,
                    port=db_port,
                )
                # Create tables using the single connection
                await self._create_tables(self._db_resource)
                logger.info("Single database connection initialized successfully.")

            else:
                raise ValueError(
                    f"Invalid DB_CONNECTION_MODE: {self._connection_mode}. Must be 'pool' or 'single'."
                )

        except ValueError as ve:  # Catch specific config errors
            logger.critical(f"Database configuration error: {ve}")
            # Re-raise or handle appropriately, maybe sys.exit here too?
            # For now, just log and raise to prevent startup
            raise
        except asyncpg.PostgresError as pe:
            logger.error(f"PostgreSQL connection error: {pe}", exc_info=True)
            await self._cleanup()
            raise
        except Exception as e:
            logger.error(
                f"Database connection initialization failed: {str(e)}", exc_info=True
            )
            await self._cleanup()  # Clean up resources
            raise

    async def _create_tables(
        self, conn_or_pool: Union[asyncpg.Pool, asyncpg.Connection]
    ):
        """Create database tables using PostgreSQL syntax if they do not exist."""
        if conn_or_pool is None:
            logger.error("Cannot create tables, database resource is not initialized.")
            return

        logger.info("Verifying/Creating database tables...")

        async def execute_schema(conn):
            # Use a transaction for schema creation
            async with conn.transaction():
                try:
                    # Users Table (PostgreSQL syntax) - Create users table first for foreign key references
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {Users.TABLE_NAME} (
                            {Users.ID} SERIAL PRIMARY KEY,
                            {Users.USERNAME} TEXT NOT NULL UNIQUE,
                            {Users.HASHED_PASSWORD} TEXT NOT NULL
                        )
                    """
                    )
                    logger.debug(f"Table {Users.TABLE_NAME} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_users_username ON {Users.TABLE_NAME} ({Users.USERNAME})
                    """
                    )
                    logger.debug(f"Index idx_users_username checked/created.")

                    # News Category Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {NewsCategory.TABLE_NAME} (
                            {NewsCategory.ID} SERIAL PRIMARY KEY,
                            {NewsCategory.NAME} TEXT NOT NULL,
                            {NewsCategory.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            UNIQUE ({NewsCategory.NAME}, {NewsCategory.USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {NewsCategory.TABLE_NAME} checked/created.")

                    # News Sources Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {NewsSource.TABLE_NAME} (
                            {NewsSource.ID} SERIAL PRIMARY KEY,
                            {NewsSource.NAME} TEXT NOT NULL,
                            {NewsSource.URL} TEXT NOT NULL,
                            {NewsSource.CATEGORY_ID} INTEGER NOT NULL,
                            {NewsSource.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            FOREIGN KEY ({NewsSource.CATEGORY_ID}) REFERENCES {NewsCategory.TABLE_NAME}({NewsCategory.ID}) ON DELETE CASCADE,
                            UNIQUE ({NewsSource.URL}, {NewsSource.USER_ID}),
                            UNIQUE ({NewsSource.NAME}, {NewsSource.USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {NewsSource.TABLE_NAME} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_sources_url ON {NewsSource.TABLE_NAME} ({NewsSource.URL})
                    """
                    )
                    logger.debug(f"Index idx_news_sources_url checked/created.")

                    # News Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {News.TABLE_NAME} (
                            {News.ID} BIGSERIAL PRIMARY KEY,
                            {News.TITLE} TEXT NOT NULL,
                            {News.URL} TEXT NOT NULL,
                            {News.SOURCE_NAME} TEXT,
                            {News.CATEGORY_NAME} TEXT,
                            {News.SOURCE_ID} INTEGER,
                            {News.CATEGORY_ID} INTEGER,
                            {News.SUMMARY} TEXT,
                            {News.ANALYSIS} TEXT,
                            {News.DATE} TEXT,
                            {News.CONTENT} TEXT,
                            {News.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            {News.CREATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- New column
                            FOREIGN KEY ({News.SOURCE_ID}) REFERENCES {NewsSource.TABLE_NAME}({NewsSource.ID}) ON DELETE SET NULL,
                            FOREIGN KEY ({News.CATEGORY_ID}) REFERENCES {NewsCategory.TABLE_NAME}({NewsCategory.ID}) ON DELETE SET NULL,
                            UNIQUE ({News.URL}, {News.USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {News.TABLE_NAME} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_url ON {News.TABLE_NAME} ({News.URL})
                    """
                    )
                    logger.debug(f"Index idx_news_url checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_date ON {News.TABLE_NAME} ({News.DATE} DESC)
                    """
                    )
                    logger.debug(f"Index idx_news_date checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_category_id ON {News.TABLE_NAME} ({News.CATEGORY_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_category_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_source_id ON {News.TABLE_NAME} ({News.SOURCE_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_source_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_user_id ON {News.TABLE_NAME} ({News.USER_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_user_id checked/created.")
                    # Optional but Recommended: Index for user_id and created_at for filtering/sorting
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_user_id_created_at ON {News.TABLE_NAME} ({News.USER_ID}, {News.CREATED_AT} DESC)
                    """
                    )
                    logger.debug(f"Index idx_news_user_id_created_at checked/created.")

                    # API Config Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {ApiConfig.TABLE_NAME} (
                            {ApiConfig.ID} SERIAL PRIMARY KEY,
                            {ApiConfig.MODEL} TEXT NOT NULL,
                            {ApiConfig.BASE_URL} TEXT NOT NULL,
                            {ApiConfig.API_KEY} TEXT NOT NULL,
                            {ApiConfig.CONTEXT} INTEGER,
                            {ApiConfig.MAX_OUTPUT_TOKENS} INTEGER,
                            {ApiConfig.DESCRIPTION} TEXT,
                            {ApiConfig.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            {ApiConfig.CREATED_DATE} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {ApiConfig.MODIFIED_DATE} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """
                    )
                    logger.debug(f"Table {ApiConfig.TABLE_NAME} checked/created.")

                    # User Preferences Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {UserPreferences.TABLE_NAME} (
                            {UserPreferences.KEY} TEXT NOT NULL,
                            {UserPreferences.VALUE} TEXT,
                            {UserPreferences.DESCRIPTION} TEXT,
                            {UserPreferences.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            PRIMARY KEY ({UserPreferences.KEY}, {UserPreferences.USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {UserPreferences.TABLE_NAME} checked/created.")

                    # Chats Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {Chats.TABLE_NAME} (
                            {Chats.ID} BIGSERIAL PRIMARY KEY,
                            {Chats.TITLE} TEXT NOT NULL,
                            {Chats.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            {Chats.CREATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {Chats.UPDATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """
                    )
                    logger.debug(f"Table {Chats.TABLE_NAME} checked/created.")

                    # Messages Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {Messages.TABLE_NAME} (
                            {Messages.ID} BIGSERIAL PRIMARY KEY,
                            {Messages.CHAT_ID} BIGINT NOT NULL,
                            {Messages.SENDER} TEXT NOT NULL,
                            {Messages.CONTENT} TEXT,
                            {Messages.TIMESTAMP} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {Messages.SEQUENCE_NUMBER} INTEGER,
                            FOREIGN KEY ({Messages.CHAT_ID}) REFERENCES {Chats.TABLE_NAME}({Chats.ID}) ON DELETE CASCADE
                        )
                    """
                    )
                    logger.debug(f"Table {Messages.TABLE_NAME} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_messages_chat_id_sequence ON {Messages.TABLE_NAME} ({Messages.CHAT_ID}, {Messages.SEQUENCE_NUMBER})
                    """
                    )
                    logger.debug(
                        f"Index idx_messages_chat_id_sequence checked/created."
                    )

                    # Fetch History Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {FetchHistory.TABLE_NAME} (
                            {FetchHistory.ID} BIGSERIAL PRIMARY KEY,
                            {FetchHistory.USER_ID} INTEGER NOT NULL REFERENCES {Users.TABLE_NAME}({Users.ID}) ON DELETE CASCADE,
                            {FetchHistory.SOURCE_ID} INTEGER NOT NULL REFERENCES {NewsSource.TABLE_NAME}({NewsSource.ID}) ON DELETE CASCADE,
                            {FetchHistory.RECORD_DATE} DATE NOT NULL,
                            {FetchHistory.ITEMS_SAVED_TODAY} INTEGER DEFAULT 0,
                            {FetchHistory.LAST_UPDATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {FetchHistory.LAST_BATCH_TASK_GROUP_ID} TEXT,
                            UNIQUE ({FetchHistory.SOURCE_ID}, {FetchHistory.USER_ID}, {FetchHistory.RECORD_DATE})
                        )
                    """
                    )
                    logger.debug(f"Table {FetchHistory.TABLE_NAME} checked/created.")

                    # Additional indexes for Fetch History table
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_fetch_history_user_id ON {FetchHistory.TABLE_NAME} ({FetchHistory.USER_ID})
                    """
                    )
                    logger.debug(f"Index idx_fetch_history_user_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_fetch_history_source_id ON {FetchHistory.TABLE_NAME} ({FetchHistory.SOURCE_ID})
                    """
                    )
                    logger.debug(f"Index idx_fetch_history_source_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_fetch_history_date ON {FetchHistory.TABLE_NAME} ({FetchHistory.RECORD_DATE})
                    """
                    )
                    logger.debug(f"Index idx_fetch_history_date checked/created.")

                    # # Add zhparser extension and config
                    # # 1. 确保 zhparser 扩展存在
                    # try:
                    #     await conn.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")
                    #     logger.debug("Extension 'zhparser' checked/created.")
                    # except asyncpg.exceptions.InsufficientPrivilegeError:
                    #     logger.warning(
                    #         "Insufficient privilege to CREATE EXTENSION zhparser. "
                    #         "Please ensure it is manually created by a superuser if not already present."
                    #     )
                    # except asyncpg.PostgresError as e_ext:
                    #     # 如果扩展已存在但由其他角色创建等情况，可能会有其他错误
                    #     # 但通常 IF NOT EXISTS 会处理好“已存在”的情况
                    #     logger.warning(
                    #         f"Notice during CREATE EXTENSION zhparser: {e_ext}. This might be okay if the extension already exists and is usable."
                    #     )

                    # # 2. 创建 zhparser 文本搜索配置
                    # zhparser_config_name = "zhparsercfg"  # 定义配置名称，方便后续使用
                    # try:
                    #     await conn.execute(
                    #         f"CREATE TEXT SEARCH CONFIGURATION {zhparser_config_name} (PARSER = zhparser);"
                    #     )
                    #     logger.info(
                    #         f"Text search configuration '{zhparser_config_name}' created."
                    #     )

                    #     # 3. 如果配置是新创建的，立即为其添加映射
                    #     # 这些映射对于 zhparser 如何处理特定类型的词元很重要
                    #     await conn.execute(
                    #         f"""
                    #         ALTER TEXT SEARCH CONFIGURATION {zhparser_config_name}
                    #         ADD MAPPING FOR n,v,a,i,e,l WITH simple;
                    #         """
                    #     )
                    #     logger.info(
                    #         f"Mappings for n,v,a,i,e,l added to new '{zhparser_config_name}'."
                    #     )

                    # except asyncpg.exceptions.DuplicateObjectError:
                    #     # 配置已经存在
                    #     logger.debug(
                    #         f"Text search configuration '{zhparser_config_name}' already exists. "
                    #         "Assuming it's correctly configured with necessary mappings. "
                    #         "If issues arise, ensure mappings (n,v,a,i,e,l WITH simple) are present."
                    #     )
                    #     # 注意：如果配置已存在，我们不再次执行 ALTER TABLE ... ADD MAPPING，
                    #     # 因为如果那些映射也已存在，它会报错。
                    #     # 一个更健壮的系统可能会检查并确保映射存在，但这会更复杂。
                    #     # 对于典型用例，如果配置存在，它通常是被正确设置的。
                    # except asyncpg.exceptions.UndefinedObjectError as e_parser_undef:
                    #     # 如果 zhparser 扩展没有成功启用，会导致这里找不到 PARSER 'zhparser'
                    #     logger.error(
                    #         f"Failed to create text search configuration '{zhparser_config_name}' "
                    #         f"because the parser 'zhparser' was not found. "
                    #         f"Please ensure the 'zhparser' extension is properly installed and enabled. Error: {e_parser_undef}"
                    #     )
                    # except asyncpg.PostgresError as e_cfg:
                    #     logger.error(
                    #         f"An error occurred while creating or configuring text search configuration '{zhparser_config_name}': {e_cfg}"
                    #     )

                    # 使用上面定义的 zhparser_config_name
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_search_fts ON {News.TABLE_NAME} USING GIN (
                            to_tsvector('zhparsercfg',
                                COALESCE({News.TITLE}, '') || ' ' ||
                                COALESCE({News.SUMMARY}, '') || ' ' ||
                                COALESCE({News.SOURCE_NAME}, '') || ' ' ||
                                COALESCE({News.CATEGORY_NAME}, '')
                            )
                        );
                    """
                    )
                    logger.debug(
                        f"Index idx_news_search_fts (GIN) for combined text fields using zhparsercfg checked/created."
                    )

                    logger.info(
                        "All database tables and indexes verified/created successfully."
                    )

                except asyncpg.PostgresError as e:
                    logger.error(f"Error creating schema: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error in schema creation: {e}")
                    raise

        if isinstance(conn_or_pool, asyncpg.Pool):
            async with conn_or_pool.acquire() as conn:
                await execute_schema(conn)
        else:
            await execute_schema(conn_or_pool)

    async def _cleanup(self):
        """Close the database connection resource (pool or single connection)."""
        if self._db_resource:
            logger.info(f"Closing database resource ({self._connection_mode} mode)...")
            try:
                if self._connection_mode == "pool":
                    await self._db_resource.close()
                    logger.info("Database connection pool closed.")
                elif self._connection_mode == "single":
                    await self._db_resource.close()
                    logger.info("Single database connection closed.")
                self._db_resource = None
                self._connection_mode = None
            except Exception as e:
                logger.error(f"Error closing database resource: {e}")

    def _cleanup_sync(self):
        """Synchronous cleanup for atexit registration."""
        import asyncio

        try:
            # Create a new event loop to run the async cleanup method
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._cleanup())
            loop.close()
        except Exception as e:
            logger.error(f"Error in _cleanup_sync: {e}")

    @asynccontextmanager
    async def get_db_connection_context(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Provides an async context manager for database connections.
        Acquires a connection from the pool in 'pool' mode, or yields the single
        connection in 'single' mode.
        """
        if self._db_resource is None:
            # If called before initialization, attempt to initialize now.
            # This might be problematic if called from a non-async context initially.
            # Best practice is to ensure init_db_connection is called during app startup.
            logger.warning(
                "Database connection manager accessed before initialization. Attempting lazy init."
            )
            await self._initialize()  # Use default mode/size if not specified

        if self._db_resource is None:  # Check again after attempting init
            raise RuntimeError("Database connection manager failed to initialize.")

        if self._connection_mode == "pool":
            # Ensure _db_resource is a pool in pool mode
            if not isinstance(self._db_resource, asyncpg.Pool):
                raise RuntimeError("Database resource is not a pool in 'pool' mode")
            async with self._db_resource.acquire() as conn:
                yield conn
        elif self._connection_mode == "single":
            # Ensure _db_resource is a connection in single mode
            if not isinstance(self._db_resource, asyncpg.Connection):
                raise RuntimeError(
                    "Database resource is not a connection in 'single' mode"
                )
            yield self._db_resource
        else:
            # This case should ideally not be reached if _initialize is called first
            raise RuntimeError(
                f"Database connection manager not initialized or invalid mode: {self._connection_mode}"
            )


# --- Helper Functions for Dependency Injection ---

_db_connection_manager: Optional[DatabaseConnectionManager] = None


async def init_db_connection(
    db_connection_mode: str = "pool",
    min_size: int = 2,
    max_size: int = 2,
) -> DatabaseConnectionManager:
    """Initialize the database connection manager."""
    global _db_connection_manager
    if _db_connection_manager is None:
        _db_connection_manager = DatabaseConnectionManager()
        await _db_connection_manager._initialize(db_connection_mode, min_size, max_size)
    return _db_connection_manager


def get_db_connection_manager() -> DatabaseConnectionManager:
    """Get the database connection manager instance."""
    global _db_connection_manager
    if _db_connection_manager is None:
        # This case might happen if get_db_connection_manager is called before init_db_connection
        # In a typical FastAPI app startup, init_db_connection should be called first.
        # However, for robustness or testing, we might initialize lazily here,
        # though the async nature of _initialize makes this tricky outside of an async context.
        # For now, assume init_db_connection is called on startup.
        # If called before init, it will return an uninitialized manager.
        # The get_db_connection_context() method will handle initialization on first use.
        _db_connection_manager = DatabaseConnectionManager()
    return _db_connection_manager


# Expose the new context manager function for dependency injection
def get_db_connection_context() -> AbstractAsyncContextManager[asyncpg.Connection]:
    """Dependency injection helper to get a database connection context manager."""
    manager = get_db_connection_manager()
    # Return the context manager instance provided by the manager
    return manager.get_db_connection_context()
