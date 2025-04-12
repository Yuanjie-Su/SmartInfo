#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database connection management module (using aiosqlite)
Responsible for creating and managing async SQLite database connections
"""

import os
import logging
import aiosqlite
from typing import Optional
import asyncio # Needed for lock

logger = logging.getLogger(__name__)


class AsyncDatabaseConnectionManager:
    """
    Async Database connection management class
    Manages a single async connection.
    """
    _instance = None
    _lock = asyncio.Lock() # Use asyncio lock
    _conn: Optional[aiosqlite.Connection] = None
    _db_path: Optional[str] = None

    # Using __await__ or an async factory might be cleaner,
    # but keeping singleton pattern similar for now. Requires careful init.
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    from backend.config import get_config
                    logger.info("Creating new AsyncDatabaseConnectionManager instance.")
                    cls._instance = cls()
                    try:
                        app_config = get_config()
                        cls._db_path = app_config.db_path
                        await cls._instance._initialize()
                    except Exception as e:
                         cls._instance = None # Reset on failure
                         logger.critical(f"Failed to initialize async DB manager: {e}", exc_info=True)
                         raise RuntimeError("Cannot create async DB connection: Initialization failed.") from e
        return cls._instance

    async def _initialize(self):
        """Initialize database connection and table structures asynchronously"""
        if self._conn is None:
            try:
                logger.info(f"Initializing aiosqlite connection to: {self._db_path}")
                # Ensure directory exists (sync is fine here during init)
                os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

                # Initialize aiosqlite connection
                self._conn = await aiosqlite.connect(self._db_path)
                # Enable WAL mode for better concurrency (recommended)
                await self._conn.execute("PRAGMA journal_mode=WAL;")
                await self._conn.commit()

                await self._create_sqlite_tables()  # Ensure table structures exist

                logger.info("Async database connection initialized successfully.")
            except Exception as e:
                logger.error(
                    f"Async database connection initialization failed: {str(e)}", exc_info=True
                )
                await self.close() # Clean up resources
                raise

    async def _create_sqlite_tables(self):
        """Create SQLite database tables asynchronously (if they do not exist)"""
        if not self._conn:
            logger.error("Cannot create tables, aiosqlite connection is not initialized.")
            return

        try:
            # Use execute() for schema changes
            # News Category Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news_category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
                """
            )
            # News Sources Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES news_category(id) ON DELETE CASCADE
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_sources_url ON news_sources (url)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_sources_category_id ON news_sources (category_id)"
            )
            # News Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL UNIQUE,
                    source_name TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    source_id INTEGER,
                    category_id INTEGER,
                    summary TEXT,
                    analysis TEXT,
                    date TEXT,
                    FOREIGN KEY (source_id) REFERENCES news_sources(id) ON DELETE SET NULL,
                    FOREIGN KEY (category_id) REFERENCES news_category(id) ON DELETE SET NULL
                );
                """
            )
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_news_link ON news (link)")
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_date ON news (date)"
            )
            # API Configuration Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_name TEXT NOT NULL UNIQUE,
                    api_key TEXT NOT NULL,
                    created_date TEXT NOT NULL,
                    modified_date TEXT NOT NULL
                )
                """
            )
            # System Configuration Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    config_key TEXT PRIMARY KEY NOT NULL,
                    config_value TEXT NOT NULL,
                    description TEXT
                )
                """
            )
            # Q&A History Table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    context_ids TEXT,
                    created_date TEXT NOT NULL
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_qa_history_created_date ON qa_history (created_date)"
            )

            await self._conn.commit()
            logger.info("Async SQLite tables verified/created successfully.")

        except aiosqlite.Error as e:
            logger.error(f"Error creating async SQLite tables: {e}", exc_info=True)
            if self._conn:
                try:
                    await self._conn.rollback()
                except aiosqlite.Error as rb_err:
                     logger.error(f"Rollback failed after table creation error: {rb_err}")
            raise

    async def close(self):
        """Clean up resources, close database connection"""
        logger.info("Closing async database connection...")
        if self._conn:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("aiosqlite connection closed.")
            except Exception as e:
                logger.error(
                    f"Error closing aiosqlite connection: {str(e)}", exc_info=True
                )
        # Reset instance for potential re-initialization if needed
        AsyncDatabaseConnectionManager._instance = None


    async def get_connection(self) -> aiosqlite.Connection:
        """Get the active aiosqlite connection object"""
        if self._conn is None or not self._conn._running: # Check if connection is active
            logger.warning("aiosqlite connection is not available or closed. Attempting to re-initialize.")
            # Attempt to re-initialize or raise an error
            await self._initialize() # Try to reconnect
            if self._conn is None:
                 raise ConnectionError("Failed to establish aiosqlite connection.")
        return self._conn


# --- Global database connection instance and getter ---
# We will initialize this during FastAPI startup using lifespan events

async def get_db() -> aiosqlite.Connection:
    """Convenience function: Get the global async SQLite connection"""
    manager = await AsyncDatabaseConnectionManager.get_instance()
    return await manager.get_connection()