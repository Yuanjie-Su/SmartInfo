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
    # Table names
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_TABLE,
    API_CONFIG_TABLE,
    USER_PREFERENCES_TABLE,
    CHATS_TABLE,
    MESSAGES_TABLE,
    USERS_TABLE,
    FETCH_HISTORY_TABLE,  # Import new table name
    # News category columns
    NEWS_CATEGORY_ID,
    NEWS_CATEGORY_NAME,
    NEWS_CATEGORY_USER_ID,
    # News source columns
    NEWS_SOURCE_ID,
    NEWS_SOURCE_NAME,
    NEWS_SOURCE_URL,
    NEWS_SOURCE_CATEGORY_ID,
    NEWS_SOURCE_USER_ID,
    # News columns
    NEWS_ID,
    NEWS_TITLE,
    NEWS_URL,
    NEWS_SOURCE_NAME,
    NEWS_CATEGORY_NAME,
    NEWS_SOURCE_ID,
    NEWS_CATEGORY_ID,
    NEWS_SUMMARY,
    NEWS_ANALYSIS,
    NEWS_DATE,
    NEWS_CONTENT,
    NEWS_USER_ID,
    # API config columns
    API_CONFIG_ID,
    API_CONFIG_MODEL,
    API_CONFIG_BASE_URL,
    API_CONFIG_API_KEY,
    API_CONFIG_CONTEXT,
    API_CONFIG_MAX_OUTPUT_TOKENS,
    API_CONFIG_DESCRIPTION,
    API_CONFIG_CREATED_DATE,
    API_CONFIG_MODIFIED_DATE,
    API_CONFIG_USER_ID,
    # User Preference columns
    USER_PREFERENCE_KEY,
    USER_PREFERENCE_VALUE,
    USER_PREFERENCE_DESCRIPTION,
    USER_PREFERENCE_USER_ID,
    # Chat columns
    CHAT_ID,
    CHAT_TITLE,
    CHAT_CREATED_AT,
    CHAT_UPDATED_AT,
    CHAT_USER_ID,
    # Message columns
    MESSAGE_ID,
    MESSAGE_CHAT_ID,
    MESSAGE_SENDER,
    MESSAGE_CONTENT,
    MESSAGE_TIMESTAMP,
    MESSAGE_SEQUENCE_NUMBER,
    # User columns
    USERS_ID,
    USERS_USERNAME,
    USERS_HASHED_PASSWORD,
    # Fetch History columns (NEW)
    FETCH_HISTORY_ID,
    FETCH_HISTORY_USER_ID,
    FETCH_HISTORY_SOURCE_ID,
    FETCH_HISTORY_RECORD_DATE,
    FETCH_HISTORY_ITEMS_SAVED_TODAY,
    FETCH_HISTORY_LAST_UPDATED_AT,
    FETCH_HISTORY_LAST_BATCH_TASK_GROUP_ID,
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
                        CREATE TABLE IF NOT EXISTS {USERS_TABLE} (
                            {USERS_ID} SERIAL PRIMARY KEY,
                            {USERS_USERNAME} TEXT NOT NULL UNIQUE,
                            {USERS_HASHED_PASSWORD} TEXT NOT NULL
                        )
                    """
                    )
                    logger.debug(f"Table {USERS_TABLE} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_users_username ON {USERS_TABLE} ({USERS_USERNAME})
                    """
                    )
                    logger.debug(f"Index idx_users_username checked/created.")

                    # News Category Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {NEWS_CATEGORY_TABLE} (
                            {NEWS_CATEGORY_ID} SERIAL PRIMARY KEY,
                            {NEWS_CATEGORY_NAME} TEXT NOT NULL,
                            {NEWS_CATEGORY_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            UNIQUE ({NEWS_CATEGORY_NAME}, {NEWS_CATEGORY_USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {NEWS_CATEGORY_TABLE} checked/created.")

                    # News Sources Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {NEWS_SOURCES_TABLE} (
                            {NEWS_SOURCE_ID} SERIAL PRIMARY KEY,
                            {NEWS_SOURCE_NAME} TEXT NOT NULL,
                            {NEWS_SOURCE_URL} TEXT NOT NULL,
                            {NEWS_SOURCE_CATEGORY_ID} INTEGER NOT NULL,
                            {NEWS_SOURCE_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            FOREIGN KEY ({NEWS_SOURCE_CATEGORY_ID}) REFERENCES {NEWS_CATEGORY_TABLE}({NEWS_CATEGORY_ID}) ON DELETE CASCADE,
                            UNIQUE ({NEWS_SOURCE_URL}, {NEWS_SOURCE_USER_ID}),
                            UNIQUE ({NEWS_SOURCE_NAME}, {NEWS_SOURCE_USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {NEWS_SOURCES_TABLE} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_sources_url ON {NEWS_SOURCES_TABLE} ({NEWS_SOURCE_URL})
                    """
                    )
                    logger.debug(f"Index idx_news_sources_url checked/created.")

                    # News Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {NEWS_TABLE} (
                            {NEWS_ID} BIGSERIAL PRIMARY KEY,
                            {NEWS_TITLE} TEXT NOT NULL,
                            {NEWS_URL} TEXT NOT NULL,
                            {NEWS_SOURCE_NAME} TEXT,
                            {NEWS_CATEGORY_NAME} TEXT,
                            {NEWS_SOURCE_ID} INTEGER,
                            {NEWS_CATEGORY_ID} INTEGER,
                            {NEWS_SUMMARY} TEXT,
                            {NEWS_ANALYSIS} TEXT,
                            {NEWS_DATE} TEXT,
                            {NEWS_CONTENT} TEXT,
                            {NEWS_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            FOREIGN KEY ({NEWS_SOURCE_ID}) REFERENCES {NEWS_SOURCES_TABLE}({NEWS_SOURCE_ID}) ON DELETE SET NULL,
                            FOREIGN KEY ({NEWS_CATEGORY_ID}) REFERENCES {NEWS_CATEGORY_TABLE}({NEWS_CATEGORY_ID}) ON DELETE SET NULL,
                            UNIQUE ({NEWS_URL}, {NEWS_USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {NEWS_TABLE} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_url ON {NEWS_TABLE} ({NEWS_URL})
                    """
                    )
                    logger.debug(f"Index idx_news_url checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_date ON {NEWS_TABLE} ({NEWS_DATE} DESC)
                    """
                    )
                    logger.debug(f"Index idx_news_date checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_category_id ON {NEWS_TABLE} ({NEWS_CATEGORY_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_category_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_source_id ON {NEWS_TABLE} ({NEWS_SOURCE_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_source_id checked/created.")
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_news_user_id ON {NEWS_TABLE} ({NEWS_USER_ID})
                    """
                    )
                    logger.debug(f"Index idx_news_user_id checked/created.")

                    # API Config Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {API_CONFIG_TABLE} (
                            {API_CONFIG_ID} SERIAL PRIMARY KEY,
                            {API_CONFIG_MODEL} TEXT NOT NULL,
                            {API_CONFIG_BASE_URL} TEXT NOT NULL,
                            {API_CONFIG_API_KEY} TEXT NOT NULL,
                            {API_CONFIG_CONTEXT} INTEGER,
                            {API_CONFIG_MAX_OUTPUT_TOKENS} INTEGER,
                            {API_CONFIG_DESCRIPTION} TEXT,
                            {API_CONFIG_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            {API_CONFIG_CREATED_DATE} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {API_CONFIG_MODIFIED_DATE} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """
                    )
                    logger.debug(f"Table {API_CONFIG_TABLE} checked/created.")

                    # User Preferences Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {USER_PREFERENCES_TABLE} (
                            {USER_PREFERENCE_KEY} TEXT NOT NULL,
                            {USER_PREFERENCE_VALUE} TEXT,
                            {USER_PREFERENCE_DESCRIPTION} TEXT,
                            {USER_PREFERENCE_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            PRIMARY KEY ({USER_PREFERENCE_KEY}, {USER_PREFERENCE_USER_ID})
                        )
                    """
                    )
                    logger.debug(f"Table {USER_PREFERENCES_TABLE} checked/created.")

                    # Chats Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {CHATS_TABLE} (
                            {CHAT_ID} BIGSERIAL PRIMARY KEY,
                            {CHAT_TITLE} TEXT NOT NULL,
                            {CHAT_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            {CHAT_CREATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {CHAT_UPDATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """
                    )
                    logger.debug(f"Table {CHATS_TABLE} checked/created.")

                    # Messages Table (PostgreSQL syntax)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
                            {MESSAGE_ID} BIGSERIAL PRIMARY KEY,
                            {MESSAGE_CHAT_ID} BIGINT NOT NULL,
                            {MESSAGE_SENDER} TEXT NOT NULL,
                            {MESSAGE_CONTENT} TEXT,
                            {MESSAGE_TIMESTAMP} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {MESSAGE_SEQUENCE_NUMBER} INTEGER,
                            FOREIGN KEY ({MESSAGE_CHAT_ID}) REFERENCES {CHATS_TABLE}({CHAT_ID}) ON DELETE CASCADE
                        )
                    """
                    )
                    logger.debug(f"Table {MESSAGES_TABLE} checked/created.")

                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_messages_chat_id_sequence ON {MESSAGES_TABLE} ({MESSAGE_CHAT_ID}, {MESSAGE_SEQUENCE_NUMBER})
                    """
                    )
                    logger.debug(
                        f"Index idx_messages_chat_id_sequence checked/created."
                    )

                    # Fetch History Table (NEW)
                    await conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {FETCH_HISTORY_TABLE} (
                            {FETCH_HISTORY_ID} BIGSERIAL PRIMARY KEY,
                            {FETCH_HISTORY_USER_ID} INTEGER NOT NULL REFERENCES {USERS_TABLE}({USERS_ID}) ON DELETE CASCADE,
                            {FETCH_HISTORY_SOURCE_ID} INTEGER NOT NULL REFERENCES {NEWS_SOURCES_TABLE}({NEWS_SOURCE_ID}) ON DELETE CASCADE,
                            {FETCH_HISTORY_RECORD_DATE} DATE NOT NULL,
                            {FETCH_HISTORY_ITEMS_SAVED_TODAY} INTEGER NOT NULL DEFAULT 0,
                            {FETCH_HISTORY_LAST_UPDATED_AT} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            {FETCH_HISTORY_LAST_BATCH_TASK_GROUP_ID} TEXT,
                            UNIQUE ({FETCH_HISTORY_USER_ID}, {FETCH_HISTORY_SOURCE_ID}, {FETCH_HISTORY_RECORD_DATE})
                        )
                        """
                    )
                    logger.debug(f"Table {FETCH_HISTORY_TABLE} checked/created.")

                    # Add index for efficient date lookup
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_fetch_history_user_date ON {FETCH_HISTORY_TABLE} ({FETCH_HISTORY_USER_ID}, {FETCH_HISTORY_RECORD_DATE} DESC)
                        """
                    )
                    logger.debug(f"Index idx_fetch_history_user_date checked/created.")

                    logger.info("Database schema verification/creation complete.")

                except asyncpg.PostgresError as e:
                    logger.error(f"Schema creation failed: {str(e)}", exc_info=True)
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
