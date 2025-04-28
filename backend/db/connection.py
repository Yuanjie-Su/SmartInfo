#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module provides a connection manager for the SQLite database.
It handles database connection, table creation, and cleanup.

The DatabaseConnectionManager class manages a single database connection and provides
methods to initialize the database, create tables, and clean up resources.
"""

import os
import logging
import aiosqlite
import atexit
from threading import Lock
from typing import Optional

# Import using backend package path
from backend.config import config
from backend.db.schema_constants import (
    # Table names
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_TABLE,
    API_CONFIG_TABLE,
    SYSTEM_CONFIG_TABLE,
    CHATS_TABLE,
    MESSAGES_TABLE,
    # News category columns
    # News source columns
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
    # System config columns
    SYSTEM_CONFIG_KEY,
    SYSTEM_CONFIG_VALUE,
    SYSTEM_CONFIG_DESCRIPTION,
    # Chat columns
    CHAT_ID,
    CHAT_TITLE,
    CHAT_CREATED_AT,
    CHAT_UPDATED_AT,
    # Message columns
    MESSAGE_ID,
    MESSAGE_CHAT_ID,
    MESSAGE_SENDER,
    MESSAGE_CONTENT,
    MESSAGE_TIMESTAMP,
    MESSAGE_SEQUENCE_NUMBER,
)

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info("Creating new DatabaseConnectionManager instance.")
                    cls._instance = super(DatabaseConnectionManager, cls).__new__(cls)
                    try:
                        cls._instance._db_path = config.db_path
                    except RuntimeError as e:
                        logger.critical(
                            f"Configuration not initialized before DB connection: {e}"
                        )
                        raise RuntimeError(
                            "Cannot create DB connection: Config not ready."
                        ) from e
                    except AttributeError as e:
                        logger.critical(
                            f"AppConfig missing expected path attributes: {e}"
                        )
                        raise RuntimeError(
                            "Cannot create DB connection: Config paths missing."
                        ) from e

                    cls._instance._connection = None
                    # 不要立即同步初始化连接，在异步上下文中再初始化
                    # 注册关闭函数到atexit
                    atexit.register(cls._instance._cleanup_sync)
        return cls._instance

    async def _initialize(self):
        """Initialize database connection and table structures"""
        if self._connection is not None:
            return

        try:
            logger.info(f"Initializing database connection to: {self._db_path}")

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

            # Connect to SQLite database using aiosqlite
            self._connection = await aiosqlite.connect(self._db_path)

            # Enable foreign keys
            await self._connection.execute("PRAGMA foreign_keys = ON")

            # Set WAL mode for better concurrency
            await self._connection.execute("PRAGMA journal_mode=WAL")

            # Create tables
            await self._create_tables()

            logger.info("Database connection initialized successfully.")

        except Exception as e:
            logger.error(
                f"Database connection initialization failed: {str(e)}", exc_info=True
            )
            await self._cleanup()  # Clean up resources
            raise

    async def _execute_schema_query(self, query_str: str) -> bool:
        """Helper to execute a single schema DDL query."""
        if not self._connection:
            logger.error("Cannot execute schema query, database is not connected.")
            return False

        try:
            async with self._connection.cursor() as cursor:
                await cursor.execute(query_str)
                await self._connection.commit()
                return True
        except aiosqlite.Error as e:
            # Ignore "table already exists" or "index already exists" errors
            if "already exists" not in str(e).lower():
                logger.error(f"Schema query failed: {query_str}\nError: {str(e)}")
                return False
            else:
                logger.debug(
                    f"Schema object already exists (ignored): {query_str.split(' ')[2]}"
                )
                return True

    async def _create_tables(self):
        """Create database tables (if they do not exist)"""
        if not self._connection:
            logger.error(
                "Cannot create tables, database connection is not initialized."
            )
            return

        logger.info("Verifying/Creating database tables...")

        # Execute each schema modification independently

        # News Category Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {NEWS_CATEGORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL UNIQUE
            )
        """
        )

        # News Sources Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {NEWS_SOURCES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL, 
                url TEXT NOT NULL UNIQUE,
                category_id INTEGER NOT NULL, 
                FOREIGN KEY (category_id) REFERENCES {NEWS_CATEGORY_TABLE}(id) ON DELETE CASCADE
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_sources_url ON {NEWS_SOURCES_TABLE} (url)
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_sources_category_id ON {NEWS_SOURCES_TABLE} (category_id)
        """
        )

        # News Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {NEWS_TABLE} (
                {NEWS_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
                {NEWS_TITLE} TEXT NOT NULL,
                {NEWS_URL} TEXT NOT NULL UNIQUE,
                {NEWS_SOURCE_NAME} TEXT NOT NULL,
                {NEWS_CATEGORY_NAME} TEXT NOT NULL,
                {NEWS_SOURCE_ID} INTEGER,
                {NEWS_CATEGORY_ID} INTEGER,
                {NEWS_SUMMARY} TEXT,
                {NEWS_ANALYSIS} TEXT,
                {NEWS_DATE} TEXT,
                {NEWS_CONTENT} TEXT,
                FOREIGN KEY ({NEWS_SOURCE_ID}) REFERENCES {NEWS_SOURCES_TABLE}(id) ON DELETE SET NULL,
                FOREIGN KEY ({NEWS_CATEGORY_ID}) REFERENCES {NEWS_CATEGORY_TABLE}(id) ON DELETE SET NULL
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_url ON {NEWS_TABLE} ({NEWS_URL})
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_date ON {NEWS_TABLE} ({NEWS_DATE})
        """
        )

        # API Configuration Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {API_CONFIG_TABLE} (
                {API_CONFIG_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
                {API_CONFIG_MODEL} TEXT NOT NULL,
                {API_CONFIG_BASE_URL} TEXT NOT NULL,
                {API_CONFIG_API_KEY} TEXT NOT NULL,
                {API_CONFIG_CONTEXT} INTEGER NOT NULL,
                {API_CONFIG_MAX_OUTPUT_TOKENS} INTEGER NOT NULL,
                {API_CONFIG_DESCRIPTION} TEXT,
                {API_CONFIG_CREATED_DATE} INTEGER NOT NULL,
                {API_CONFIG_MODIFIED_DATE} INTEGER NOT NULL
            )
        """
        )

        # System Config Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {SYSTEM_CONFIG_TABLE} (
                {SYSTEM_CONFIG_KEY} TEXT PRIMARY KEY NOT NULL,
                {SYSTEM_CONFIG_VALUE} TEXT NOT NULL,
                {SYSTEM_CONFIG_DESCRIPTION} TEXT
            )
        """
        )

        # Chats Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {CHATS_TABLE} (
                {CHAT_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {CHAT_TITLE} TEXT NOT NULL,
                {CHAT_CREATED_AT} INTEGER NOT NULL,
                {CHAT_UPDATED_AT} INTEGER
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_chats_created_at ON {CHATS_TABLE} ({CHAT_CREATED_AT})
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON {CHATS_TABLE} ({CHAT_UPDATED_AT})
        """
        )

        # Messages Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
                {MESSAGE_ID} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {MESSAGE_CHAT_ID} INTEGER NOT NULL,
                {MESSAGE_SENDER} TEXT NOT NULL,
                {MESSAGE_CONTENT} TEXT NOT NULL,
                {MESSAGE_TIMESTAMP} INTEGER NOT NULL,
                {MESSAGE_SEQUENCE_NUMBER} INTEGER NOT NULL,
                FOREIGN KEY ({MESSAGE_CHAT_ID}) REFERENCES {CHATS_TABLE}(id) ON DELETE CASCADE
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON {MESSAGES_TABLE} ({MESSAGE_CHAT_ID})
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON {MESSAGES_TABLE} ({MESSAGE_TIMESTAMP})
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_seq ON {MESSAGES_TABLE} ({MESSAGE_CHAT_ID}, {MESSAGE_SEQUENCE_NUMBER})
        """
        )

        logger.info("Database tables checked/created successfully.")

    async def _cleanup(self):
        """Clean up database resources"""
        if self._connection:
            logger.info("Closing database connection...")
            try:
                await self._connection.close()
                self._connection = None
                logger.info("Database connection closed.")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")

    def _cleanup_sync(self):
        """同步版本的cleanup，用于atexit注册"""
        import asyncio

        try:
            # 创建一个新的事件循环来运行异步清理方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._cleanup())
            loop.close()
        except Exception as e:
            logger.error(f"Error in _cleanup_sync: {e}")

    async def get_connection(self) -> aiosqlite.Connection:
        """Get a connection to the database."""
        if self._connection is None:
            await self._initialize()
        return self._connection


# --- Helper Functions for Dependency Injection ---

_db_connection_manager = None


async def init_db_connection() -> DatabaseConnectionManager:
    """Initialize the database connection manager."""
    global _db_connection_manager
    if _db_connection_manager is None:
        _db_connection_manager = DatabaseConnectionManager()
        await _db_connection_manager._initialize()
    return _db_connection_manager


def get_db_connection_manager() -> DatabaseConnectionManager:
    """Get the database connection manager instance."""
    global _db_connection_manager
    if _db_connection_manager is None:
        _db_connection_manager = DatabaseConnectionManager()
    return _db_connection_manager


async def get_db_connection() -> aiosqlite.Connection:
    """Get a connection to the database.
    This is the primary function used for dependency injection."""
    manager = get_db_connection_manager()
    return await manager.get_connection()
