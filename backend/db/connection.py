#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database connection management module
Responsible for creating and managing SQLite database connections
Uses singleton pattern to ensure connections are reused throughout the application lifecycle
"""

import os
import logging
import sqlite3
from typing import Optional
import atexit
from threading import Lock
import time

# Get paths from unified configuration
from backend.config import get_config

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """
    Database connection management class, implements singleton pattern
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info("Creating new DatabaseConnectionManager instance.")
                    cls._instance = super(DatabaseConnectionManager, cls).__new__(cls)
                    # Ensure configuration is loaded before initializing instance variables
                    try:
                        app_config = get_config()
                        cls._instance._sqlite_db_path = app_config.db_path
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

                    cls._instance._sqlite_conn = None
                    cls._instance._initialize()
                    # Register cleanup function on program exit
                    atexit.register(cls._instance._cleanup)
        return cls._instance

    def _initialize(self):
        """Initialize database connections and table structures"""
        try:
            logger.info(f"Initializing SQLite connection to: {self._sqlite_db_path}")
            # Initialize SQLite connection
            # check_same_thread=False is suitable for multi-threaded access, but be cautious with transaction management
            self._sqlite_conn = sqlite3.connect(
                self._sqlite_db_path, check_same_thread=False
            )
            self._create_sqlite_tables()  # Ensure table structures exist

            logger.info("Database connections initialized successfully.")
        except Exception as e:
            logger.error(
                f"Database connection initialization failed: {str(e)}", exc_info=True
            )
            self._cleanup()  # Clean up resources that may have been created
            raise

    def _create_sqlite_tables(self):
        """Create SQLite database tables (if they do not exist)"""
        if not self._sqlite_conn:
            logger.error("Cannot create tables, SQLite connection is not initialized.")
            return

        try:
            cursor = self._sqlite_conn.cursor()

            # News Category Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS news_category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
                """
            )

            # News Sources Table
            cursor.execute(
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
            # Add index for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_sources_url ON news_sources (url)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_sources_category_id ON news_sources (category_id)"
            )

            # News Table
            cursor.execute(
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
            # Add indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_link ON news (link)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_date ON news (date)"
            )

            # API Configuration Table (for storing API keys - consider security implications)
            # Storing API keys directly in DB might not be the most secure method.
            # Environment variables or a dedicated secrets manager are often preferred.
            cursor.execute(
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    config_key TEXT PRIMARY KEY NOT NULL,
                    config_value TEXT NOT NULL,
                    description TEXT
                )
                """
            )

            # Q&A History Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    context_ids TEXT,            -- Comma-separated string of related news IDs
                    created_date TEXT NOT NULL
                )
                """
            )
            # Add index
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_qa_history_created_date ON qa_history (created_date)"
            )

            # Set journal mode to WAL for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")

            self._sqlite_conn.commit()
            logger.info("SQLite tables verified/created successfully.")

        except sqlite3.Error as e:
            logger.error(f"Error creating SQLite tables: {e}", exc_info=True)
            if self._sqlite_conn:
                self._sqlite_conn.rollback()
            raise  # Re-raise the exception

    def _cleanup(self):
        """Clean up resources, close database connections"""
        logger.info("Cleaning up database connections...")
        if self._sqlite_conn:
            try:
                self._sqlite_conn.close()
                self._sqlite_conn = None
                logger.info("SQLite connection closed.")
            except Exception as e:
                logger.error(
                    f"Error closing SQLite connection: {str(e)}", exc_info=True
                )

    def get_sqlite_connection(self) -> sqlite3.Connection:
        """Get SQLite database connection object"""
        if self._sqlite_conn is None:
            logger.error("SQLite connection is not available.")
            # Attempt to re-initialize or raise an error
            self._initialize()  # Try to reconnect
            if self._sqlite_conn is None:
                raise ConnectionError("Failed to establish SQLite connection.")
        return self._sqlite_conn


# --- Global database connection instance ---
# Initialized in main.py
_db_manager: Optional[DatabaseConnectionManager] = None


def init_db_connection() -> DatabaseConnectionManager:
    """Initialize global database connection manager"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseConnectionManager()
    return _db_manager


def get_db_connection_manager() -> DatabaseConnectionManager:
    """Get global database connection manager instance"""
    if _db_manager is None:
        raise RuntimeError(
            "Database connection not initialized. Call init_db_connection() first."
        )
    return _db_manager


def get_db() -> sqlite3.Connection:
    """Convenience function: Get SQLite connection"""
    return get_db_connection_manager().get_sqlite_connection()

