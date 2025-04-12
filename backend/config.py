#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Project configuration module
Manage the global configuration of the application
Prioritize loading sensitive information (such as API Key) from environment variables, followed by loading persistent configuration from the database.
"""

import os
import json
import logging
import sqlite3
import aiosqlite
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
DEFAULT_SQLITE_DB_NAME = "smartinfo.db"

# --- Configuration Keys ---
# Environment variables take precedence
API_KEY_DEEPSEEK = "API_KEY_DEEPSEEK"  # Read from .env
API_KEY_VOLCENGINE = "API_KEY_VOLCENGINE"  # Read from .env
# Database configuration keys
CONFIG_KEY_DATA_DIR = "data_dir"
CONFIG_KEY_FETCH_FREQUENCY = "fetch_frequency"
CONFIG_KEY_UI_THEME = "ui_theme"
CONFIG_KEY_LANGUAGE = "language"


class AppConfig:
    """Application configuration class"""

    # Default configuration (persistent part)
    DEFAULT_PERSISTENT_CONFIG = {
        CONFIG_KEY_DATA_DIR: DEFAULT_DATA_DIR,
        CONFIG_KEY_FETCH_FREQUENCY: "manual",
        CONFIG_KEY_UI_THEME: "light",
        CONFIG_KEY_LANGUAGE: "zh_CN",
    }

    def __init__(self):
        """Initialize configuration (Sync Load, Async Save support)"""
        self._persistent_config: Dict[str, Any] = self.DEFAULT_PERSISTENT_CONFIG.copy()
        self._secrets: Dict[str, Optional[str]] = {}

        self._load_secrets_from_env()

        # Determine initial data directory (sync)
        self._data_dir = self._persistent_config[CONFIG_KEY_DATA_DIR]
        self._ensure_data_dir() # Sync check/create
        self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)

        # Load from DB SYNCHRONOUSLY during init
        self._load_from_db_sync()

        # Confirm final data directory (sync)
        self._data_dir = self._persistent_config[CONFIG_KEY_DATA_DIR]
        self._ensure_data_dir()
        self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)

        logger.info(f"Configuration initialized. Data Dir: {self._data_dir}")
        logger.info(f"Database Path: {self._db_path}")
        logger.info(f"Loaded secrets keys: {list(self._secrets.keys())}")

    def _load_secrets_from_env(self):
        """Load sensitive configuration from environment variables"""
        self._secrets[API_KEY_DEEPSEEK] = os.getenv("DEEPSEEK_API_KEY")
        if not self._secrets[API_KEY_DEEPSEEK]:
            logger.warning(
                "DEEPSEEK_API_KEY not found in environment variables or .env file."
            )
        self._secrets[API_KEY_VOLCENGINE] = os.getenv("VOLCENGINE_API_KEY")
        if not self._secrets[API_KEY_VOLCENGINE]:
            logger.warning(
                "VOLCENGINE_API_KEY not found in environment variables or .env file."
            )

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists"""
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except OSError as e:
            logger.error(
                f"Failed to create data directory {self._data_dir}: {e}", exc_info=True
            )
            # May need to take alternative measures or exit
            raise

    def _load_from_db_sync(self) -> None:
        """Load persistent configuration from the database SYNCHRONOUSLY."""
        # Uses standard sqlite3 for startup load before async loop starts
        if not os.path.exists(self._db_path):
            logger.info("Database file does not exist, using default persistent config.")
            return

        conn = None
        try:
            conn = sqlite3.connect(self._db_path) # Use sync connect
            cursor = conn.cursor()
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            if not cursor.fetchone():
                logger.info("system_config table does not exist, using default persistent config.")
                return

            cursor.execute("SELECT config_key, config_value FROM system_config")
            rows = cursor.fetchall()
            loaded_config = {}
            for key, value in rows:
                if key in self.DEFAULT_PERSISTENT_CONFIG:
                    try:
                        loaded_config[key] = json.loads(value)
                    except json.JSONDecodeError:
                        loaded_config[key] = value
                else:
                     logger.warning(f"Ignoring unknown config key '{key}' from database during sync load.")

            for key in self.DEFAULT_PERSISTENT_CONFIG:
                 if key in loaded_config:
                    self._persistent_config[key] = loaded_config[key]

            logger.info("Successfully loaded configuration from database (synchronously).")

        except sqlite3.Error as e:
            logger.error(f"Failed to load configuration from database (sync) '{self._db_path}': {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value (prioritize getting from secrets, then persistent_config)
        """
        if key in self._secrets:
            return self._secrets[key]
        return self._persistent_config.get(key, default)

    def get_persistent(self, key: str, default: Any = None) -> Any:
        """Get only persistent configuration value"""
        return self._persistent_config.get(key, default)

    def set_persistent(self, key: str, value: Any) -> None:
        """
        Set persistent configuration value (will not be immediately saved to database, must call save)
        Only allows setting keys defined in DEFAULT_PERSISTENT_CONFIG
        """
        if key in self.DEFAULT_PERSISTENT_CONFIG:
            self._persistent_config[key] = value
            # If setting data_dir, need to update internal paths
            if key == CONFIG_KEY_DATA_DIR:
                self._data_dir = value
                self._ensure_data_dir()
                self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)
                logger.info(f"Data directory updated to: {self._data_dir}")
                logger.info(f"Database path updated to: {self._db_path}")
        else:
            logger.warning(
                f"Attempted to set unknown or non-persistent config key: {key}"
            )

    async def save_persistent(self) -> bool:
        """
        Save the persistent configuration in memory to the database ASYNCHRONOUSLY.
        """
        from backend.db.connection import get_db
        conn = None
        try:
            # Ensure directory exists (sync check is ok before async connect)
            self._ensure_data_dir()
            conn = await get_db() # Get async connection

            # Ensure table exists (async execute)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    config_key TEXT PRIMARY KEY NOT NULL,
                    config_value TEXT NOT NULL,
                    description TEXT
                )
                """
            )

            config_to_save = []
            for key, value in self._persistent_config.items():
                try:
                    json_value = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    json_value = str(value)
                config_to_save.append((key, json_value))

            # Use async executemany and commit
            await conn.executemany(
                "INSERT OR REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)",
                config_to_save,
            )
            await conn.commit()

            logger.info("Successfully saved persistent configuration to database (asynchronously).")
            return True
        except aiosqlite.Error as e:
            logger.error(f"Failed to save configuration to database (async) '{self._db_path}': {e}", exc_info=True)
            if conn:
                try:
                    await conn.rollback() # Async rollback
                except Exception as rb_err:
                     logger.error(f"Async rollback failed after config save error: {rb_err}")
            return False

    def reset_persistent_to_defaults(self) -> None:
        """Reset persistent configuration to default values (in memory)"""
        self._persistent_config = self.DEFAULT_PERSISTENT_CONFIG.copy()
        # After resetting, also need to update internal paths
        self._data_dir = self._persistent_config[CONFIG_KEY_DATA_DIR]
        self._ensure_data_dir()
        self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)
        logger.info("Persistent configuration reset to defaults in memory.")

    @property
    def data_dir(self) -> str:
        """Get the data storage directory"""
        return self._data_dir

    @property
    def db_path(self) -> str:
        """Get the full path of the SQLite database"""
        return self._db_path


# --- Global configuration instance ---
# Initialized in main.py
_global_config: Optional[AppConfig] = None


def init_config() -> AppConfig:
    """Initialize global configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = AppConfig()
    return _global_config


def get_config() -> AppConfig:
    """Get global configuration instance (must call init_config first)"""
    if _global_config is None:
        raise RuntimeError("Configuration not initialized. Call init_config() first.")
    return _global_config
