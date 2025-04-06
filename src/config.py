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
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load .env file (ensure there is a .env file in the project root directory)
load_dotenv()

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
DEFAULT_SQLITE_DB_NAME = "smartinfo.db"

# --- Configuration Keys ---
# Environment variables take precedence
API_KEY_DEEPSEEK = "API_KEY_DEEPSEEK"  # Read from .env

# Database configuration keys
CONFIG_KEY_DATA_DIR = "data_dir"
CONFIG_KEY_FETCH_FREQUENCY = "fetch_frequency"
CONFIG_KEY_EMBEDDING_MODEL = "embedding_model"
CONFIG_KEY_UI_THEME = "ui_theme"
CONFIG_KEY_LANGUAGE = "language"


class AppConfig:
    """Application configuration class"""

    # Default configuration (persistent part)
    DEFAULT_PERSISTENT_CONFIG = {
        CONFIG_KEY_DATA_DIR: DEFAULT_DATA_DIR,
        CONFIG_KEY_FETCH_FREQUENCY: "manual",
        CONFIG_KEY_EMBEDDING_MODEL: "sentence-transformers/all-MiniLM-L6-v2",
        CONFIG_KEY_UI_THEME: "light",
        CONFIG_KEY_LANGUAGE: "zh_CN",
    }

    def __init__(self):
        """Initialize configuration"""
        # Store persistent configuration loaded from DB
        self._persistent_config: Dict[str, Any] = self.DEFAULT_PERSISTENT_CONFIG.copy()
        # Store sensitive configuration loaded from environment variables
        self._secrets: Dict[str, Optional[str]] = {}

        # 1. Load environment variables (Secrets)
        self._load_secrets_from_env()

        # 2. Determine data directory and database path (must be done before loading DB configuration)
        self._data_dir = self._persistent_config[
            CONFIG_KEY_DATA_DIR
        ]  # Initial default value
        self._ensure_data_dir()  # Ensure the directory exists
        self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)

        # 3. Load database configuration (will override default values, including data_dir)
        self._load_from_db()

        # 4. Confirm data directory again (as it may have been overridden by DB configuration)
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

    def _load_from_db(self) -> None:
        """Load persistent configuration from the database"""
        if not os.path.exists(self._db_path):
            logger.info(
                "Database file does not exist, using default persistent config."
            )
            return

        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'"
            )
            if not cursor.fetchone():
                logger.info(
                    "system_config table does not exist, using default persistent config."
                )
                return

            cursor.execute("SELECT config_key, config_value FROM system_config")
            rows = cursor.fetchall()

            loaded_config = {}
            for key, value in rows:
                if (
                    key in self.DEFAULT_PERSISTENT_CONFIG
                ):  # Only load predefined persistent configuration items
                    try:
                        # Attempt to parse the value as a JSON object
                        loaded_config[key] = json.loads(value)
                    except json.JSONDecodeError:
                        # If not JSON, use the string value directly
                        loaded_config[key] = value
                else:
                    logger.warning(
                        f"Ignoring unknown config key '{key}' from database."
                    )

            # Update the configuration in memory, but do not overwrite keys not in the default values
            for key in self.DEFAULT_PERSISTENT_CONFIG:
                if key in loaded_config:
                    self._persistent_config[key] = loaded_config[key]

            logger.info("Successfully loaded configuration from database.")

        except sqlite3.Error as e:
            logger.error(
                f"Failed to load configuration from database '{self._db_path}': {e}",
                exc_info=True,
            )
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

    def save_persistent(self) -> bool:
        """
        Save the persistent configuration in memory to the database
        """
        conn = None
        try:
            self._ensure_data_dir()  # Ensure the directory exists
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute(
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
                # Convert the value to a JSON string for storage
                try:
                    json_value = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    json_value = str(value)  # Fallback to string

                config_to_save.append((key, json_value))

            # Use INSERT OR REPLACE (or ON CONFLICT UPDATE) to update or insert
            cursor.executemany(
                "INSERT OR REPLACE INTO system_config (config_key, config_value) VALUES (?, ?)",
                config_to_save,
            )

            conn.commit()
            logger.info("Successfully saved persistent configuration to database.")
            return True
        except sqlite3.Error as e:
            logger.error(
                f"Failed to save configuration to database '{self._db_path}': {e}",
                exc_info=True,
            )
            if conn:
                conn.rollback()  # Rollback changes
            return False
        finally:
            if conn:
                conn.close()

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

    @property
    def chroma_db_path(self) -> str:
        """Get the storage path of ChromaDB"""
        # ChromaDB path is usually under data_dir
        return os.path.join(self._data_dir, "chromadb")


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
