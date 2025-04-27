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
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_TABLE,
    API_CONFIG_TABLE,
    SYSTEM_CONFIG_TABLE,
    CHATS_TABLE,
    MESSAGES_TABLE,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source_name TEXT NOT NULL,
                category_name TEXT NOT NULL,
                source_id INTEGER,
                category_id INTEGER,
                summary TEXT,
                analysis TEXT,
                date TEXT,
                content TEXT,
                FOREIGN KEY (source_id) REFERENCES {NEWS_SOURCES_TABLE}(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES {NEWS_CATEGORY_TABLE}(id) ON DELETE SET NULL
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_url ON {NEWS_TABLE} (url)
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_date ON {NEWS_TABLE} (date)
        """
        )

        # API Configuration Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {API_CONFIG_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL UNIQUE,
                api_key TEXT NOT NULL,
                description TEXT,
                created_date INTEGER NOT NULL,
                modified_date INTEGER NOT NULL
            )
        """
        )

        # System Config Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {SYSTEM_CONFIG_TABLE} (
                config_key TEXT PRIMARY KEY NOT NULL,
                config_value TEXT NOT NULL,
                description TEXT
            )
        """
        )

        # Chats Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {CHATS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                title TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_chats_created_at ON {CHATS_TABLE} (created_at)
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON {CHATS_TABLE} (updated_at)
        """
        )

        # Messages Table
        await self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {MESSAGES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                chat_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                sequence_number INTEGER NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES {CHATS_TABLE}(id) ON DELETE CASCADE
            )
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON {MESSAGES_TABLE} (chat_id)
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON {MESSAGES_TABLE} (timestamp)
        """
        )

        await self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_seq ON {MESSAGES_TABLE} (chat_id, sequence_number)
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
