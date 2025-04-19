# src/db/connection.py (Rewritten for PySide6.QtSql)
# -*- coding: utf-8 -*-

"""
This module provides a connection manager for the SQLite database using PySide6.QtSql.
It handles database connection, table creation, and cleanup.

The DatabaseConnectionManager class manages a single database connection and provides
methods to initialize the database, create tables, and clean up resources.

"""

import os
import logging
import atexit
from threading import Lock
from typing import Optional

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from src.config import get_config
from src.db.schema_constants import (
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_TABLE,
    API_CONFIG_TABLE,
    SYSTEM_CONFIG_TABLE,
    QA_HISTORY_TABLE,
)

logger = logging.getLogger(__name__)

# Use a fixed connection name for the main application connection
MAIN_DB_CONNECTION_NAME = "main_smartinfo_connection"


class DatabaseConnectionManager:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info("Creating new Qt DatabaseConnectionManager instance.")
                    cls._instance = super(DatabaseConnectionManager, cls).__new__(cls)
                    try:
                        app_config = get_config()
                        cls._instance._db_path = app_config.db_path
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

                    cls._instance._qt_database = None
                    cls._instance._initialize()
                    atexit.register(cls._instance._cleanup)
        return cls._instance

    def _initialize(self):
        """Initialize QtSql database connection and table structures"""
        try:
            logger.info(f"Initializing Qt database connection to: {self._db_path}")

            # Check if connection already exists, otherwise add it
            if QSqlDatabase.contains(MAIN_DB_CONNECTION_NAME):
                self._qt_database = QSqlDatabase.database(MAIN_DB_CONNECTION_NAME)
                if not self._qt_database.isOpen():
                    logger.warning(
                        f"Existing Qt connection '{MAIN_DB_CONNECTION_NAME}' was closed. Reopening."
                    )
                    if not self._qt_database.open():
                        raise ConnectionError(
                            f"Failed to reopen Qt database: {self._qt_database.lastError().text()}"
                        )
                else:
                    logger.info(
                        f"Reusing existing Qt connection: {MAIN_DB_CONNECTION_NAME}"
                    )

            else:
                self._qt_database = QSqlDatabase.addDatabase(
                    "QSQLITE", MAIN_DB_CONNECTION_NAME
                )
                self._qt_database.setDatabaseName(self._db_path)
                if not self._qt_database.open():
                    raise ConnectionError(
                        f"Failed to open Qt database: {self._qt_database.lastError().text()}"
                    )

            # Set WAL mode for better concurrency (recommended for SQLite with QtSql)
            # Issue #1: Make sure this is executed as a direct query before any transaction begins
            query_wal = QSqlQuery(self._qt_database)
            if not query_wal.exec("PRAGMA journal_mode=WAL;"):
                logger.warning(
                    f"Could not set journal_mode=WAL: {query_wal.lastError().text()}"
                )
            else:
                # Verify WAL mode was set
                query_check = QSqlQuery(self._qt_database)
                if query_check.exec("PRAGMA journal_mode;"):
                    if query_check.next():
                        mode = query_check.value(0).lower()
                        logger.info(f"SQLite journal mode set to: {mode}")
                        if mode != "wal":
                            logger.warning(
                                f"Journal mode is {mode}, not WAL as expected"
                            )
                    else:
                        logger.warning("Could not retrieve journal mode value")
                else:
                    logger.warning("Could not check journal mode setting")
                query_check.finish()

            # Ensure WAL mode query is finished before proceeding
            query_wal.finish()

            self._create_tables()  # Ensure table structures exist

            logger.info("Qt Database connection initialized successfully.")

        except Exception as e:
            logger.error(
                f"Qt Database connection initialization failed: {str(e)}", exc_info=True
            )
            self._cleanup()  # Clean up resources
            raise

    def _execute_schema_query(self, query_str: str) -> bool:
        """Helper to execute a single schema DDL query."""
        if not self._qt_database or not self._qt_database.isOpen():
            logger.error("Cannot execute schema query, Qt database is not open.")
            return False

        # Create query object within a local scope
        query = QSqlQuery(self._qt_database)
        success = query.exec(query_str)  # Directly execute

        if not success:
            error_text = query.lastError().text()
            # Ignore "table already exists" or "index already exists" errors
            if "already exists" not in error_text.lower():
                logger.error(f"Schema query failed: {query_str}\nError: {error_text}")
                query.finish()  # Explicitly finish the query before returning
                return False
            else:
                logger.debug(
                    f"Schema object already exists (ignored): {query_str.split(' ')[2]}"
                )

        # Explicitly finish the query to release resources
        query.finish()
        return True

    def _create_tables(self):
        """Create database tables using QSqlQuery (if they do not exist)"""
        if not self._qt_database or not self._qt_database.isOpen():
            logger.error(
                "Cannot create tables, Qt database connection is not initialized."
            )
            return

        logger.info("Verifying/Creating database tables...")

        # Execute each schema modification independently (no transaction)
        # This avoids issues with SQL statements in progress during commit

        # News Category Table
        self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {NEWS_CATEGORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL UNIQUE
            )
        """
        )

        # News Sources Table
        self._execute_schema_query(
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

        self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_sources_url ON {NEWS_SOURCES_TABLE} (url)
        """
        )

        self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_sources_category_id ON {NEWS_SOURCES_TABLE} (category_id)
        """
        )

        # News Table
        self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {NEWS_TABLE} (
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
                content TEXT,
                FOREIGN KEY (source_id) REFERENCES {NEWS_SOURCES_TABLE}(id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES {NEWS_CATEGORY_TABLE}(id) ON DELETE SET NULL
            )
        """
        )

        self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_link ON {NEWS_TABLE} (link)
        """
        )

        self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_news_date ON {NEWS_TABLE} (date)
        """
        )

        # API Configuration Table
        self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {API_CONFIG_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL UNIQUE,
                api_key TEXT NOT NULL,
                created_date TEXT NOT NULL,
                modified_date TEXT NOT NULL
            )
        """
        )

        # System Configuration Table
        self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {SYSTEM_CONFIG_TABLE} (
                config_key TEXT PRIMARY KEY NOT NULL,
                config_value TEXT NOT NULL,
                description TEXT
            )
        """
        )

        # Q&A History Table
        self._execute_schema_query(
            f"""
            CREATE TABLE IF NOT EXISTS {QA_HISTORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                context_ids TEXT,
                created_date TEXT NOT NULL
            )
        """
        )

        self._execute_schema_query(
            f"""
            CREATE INDEX IF NOT EXISTS idx_qa_history_created_date ON {QA_HISTORY_TABLE} (created_date)
        """
        )

        logger.info("Database tables verified/created successfully.")

    def _cleanup(self):
        """Clean up resources, close database connection"""
        logger.info("Cleaning up Qt database connection...")
        if self._qt_database:
            conn_name = self._qt_database.connectionName()

            # 先关闭连接
            if self._qt_database.isOpen():
                try:
                    self._qt_database.close()
                    logger.info(f"Qt database connection '{conn_name}' closed.")
                except Exception as e:
                    logger.error(
                        f"Error closing Qt database connection: {str(e)}", exc_info=True
                    )

            # 释放引用
            self._qt_database = None

            # 然后从连接池移除
            try:
                QSqlDatabase.removeDatabase(conn_name)
                logger.info(f"Qt database connection '{conn_name}' removed.")
            except Exception as e:
                logger.error(
                    f"Error removing Qt database connection: {str(e)}", exc_info=True
                )

    def get_qt_database(self) -> QSqlDatabase:
        """Get the main QtSql database connection object"""
        if self._qt_database is None or not self._qt_database.isValid():
            logger.error("Qt database connection is not available or invalid.")
            # Attempt to re-initialize
            self._initialize()
            if self._qt_database is None or not self._qt_database.isValid():
                raise ConnectionError("Failed to establish Qt database connection.")
        elif not self._qt_database.isOpen():
            logger.warning(
                f"Qt database connection '{self._qt_database.connectionName()}' was closed. Attempting to reopen."
            )
            if not self._qt_database.open():
                raise ConnectionError(
                    f"Failed to reopen Qt database: {self._qt_database.lastError().text()}"
                )
        return self._qt_database


# --- Global database connection instance ---
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


def get_db() -> QSqlDatabase:
    """Convenience function: Get the main QSqlDatabase connection"""
    return get_db_connection_manager().get_qt_database()
