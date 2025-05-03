# backend/config.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Application Configuration Module
- Loads settings from environment variables and a system configuration table in the database.
- Provides access to configuration values throughout the application.
"""

import logging
import os
from typing import Any, Optional, Dict, Type, TYPE_CHECKING

# Configure module-level logger
logger = logging.getLogger(__name__)

# Type hint for repository to avoid circular import issues
if TYPE_CHECKING:
    from db.repositories.system_config_repository import SystemConfigRepository

# --- Constants ---
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
DEFAULT_SQLITE_DB_NAME = "smartinfo.db"


class AppConfig:
    """
    Manages application configuration settings.
    Settings are loaded from:
    1. Environment variables (highest priority)
    2. Database (for persistent settings)
    3. Default values defined here (lowest priority)
    """

    # Define keys, default values, and their expected types for persistent settings
    DEFAULT_PERSISTENT_CONFIG: Dict[str, tuple[Any, Type]] = {
        "LLM_API_KEY": (None, str),  # Sensitive, prioritize ENV
        "LLM_BASE_URL": ("https://api.deepseek.com", str),  # Example default
        "LLM_MODEL": ("deepseek-v3-250324", str),  # Default model
        "LLM_POOL_SIZE": (3, int),  # Default pool size
    }

    def __init__(self):
        """Initialize configuration."""
        self._db_config: Dict[str, Any] = (
            {}
        )  # In-memory store for persistent settings loaded from DB
        self._system_config_repo: Optional["SystemConfigRepository"] = (
            None  # DB repository reference
        )

        # Get data directory from environment variable or use default
        self._data_dir = os.environ.get("SMARTINFO_DATA_DIR", DEFAULT_DATA_DIR)

        # Ensure the data directory exists
        self._ensure_data_dir()

        # Set database path by combining data directory and database filename
        self._db_path = os.path.join(self._data_dir, DEFAULT_SQLITE_DB_NAME)

        logger.info(f"Data directory configured to: {self._data_dir}")
        logger.info(f"Database path configured to: {self._db_path}")

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists"""
        if not os.path.exists(self._data_dir):
            try:
                os.makedirs(self._data_dir)
                logger.info(f"Created data directory: {self._data_dir}")
            except OSError as e:
                logger.error(f"Failed to create data directory {self._data_dir}: {e}")

    async def set_db_repo(self, system_config_repo: "SystemConfigRepository"):
        """
        Set the SystemConfigRepository instance and load settings from the database.
        This should be called once the database connection is available.
        """
        if self._system_config_repo:
            logger.warning("SystemConfigRepository is being reset.")
        self._system_config_repo = system_config_repo
        await self._load_from_database()

    async def _load_from_database(self):
        """
        Load persistent configuration from the database using the repository.
        Ensures default persistent settings exist in the DB if they are missing.
        """
        if not self._system_config_repo:
            logger.error("Cannot load from database: SystemConfigRepository not set.")
            return

        try:
            db_settings_raw = (
                await self._system_config_repo.get_all()
            )  # Returns {key: value_str}
            self._db_config = {}  # Reset in-memory store

            for key, value_str in db_settings_raw.items():
                if key in self.DEFAULT_PERSISTENT_CONFIG:
                    _, expected_type = self.DEFAULT_PERSISTENT_CONFIG[key]
                    try:
                        # Attempt type conversion based on expected type
                        if expected_type == bool:
                            value = value_str.lower() in ("true", "1", "yes")
                        elif expected_type == int:
                            value = int(value_str)
                        elif expected_type == float:
                            value = float(value_str)
                        else:  # Default to string
                            value = str(value_str)  # Ensure it's a string
                        self._db_config[key] = value
                    except (ValueError, TypeError) as conversion_error:
                        logger.warning(
                            f"Could not convert DB value for key '{key}' ('{value_str}') to "
                            f"expected type {expected_type}. Using raw string value. Error: {conversion_error}"
                        )
                        self._db_config[key] = value_str  # Fallback to raw string
                else:
                    logger.debug(f"Ignoring unknown setting '{key}' found in database.")

            logger.info(f"Loaded {len(self._db_config)} settings from database.")

            # Ensure default persistent settings exist in DB
            await self._ensure_default_persistent_settings()

        except Exception as e:
            logger.exception("Error loading configuration from database", exc_info=True)
            self._db_config = {}  # Reset on error

    async def _ensure_default_persistent_settings(self):
        """Ensure default persistent settings exist in the database."""
        if not self._system_config_repo:
            return  # Cannot proceed without repo

        added_count = 0
        try:
            for key, (default_value, _) in self.DEFAULT_PERSISTENT_CONFIG.items():
                # Check if the setting exists in the DB config loaded into memory
                if key not in self._db_config:
                    # If default value is None, don't add it unless explicitly set later
                    if default_value is not None:
                        logger.info(
                            f"Default setting '{key}' not found in DB. Adding with value: {default_value}"
                        )
                        # Use the repository's 'set' method to add/update individually
                        success = await self._system_config_repo.set(
                            key, str(default_value)
                        )
                        if success:
                            # Update in-memory cache as well
                            self._db_config[key] = default_value
                            added_count += 1
                        else:
                            logger.error(
                                f"Failed to add default setting '{key}' to database."
                            )
                    else:
                        # If default is None, ensure it's not lingering in memory either
                        if key in self._db_config:
                            del self._db_config[key]

            if added_count > 0:
                logger.info(
                    f"Ensured/Added {added_count} default persistent settings in database."
                )

        except Exception as e:
            logger.exception(
                "Error ensuring default persistent settings in database", exc_info=True
            )

    def save_persistent(self) -> bool:
        """
        Save the current in-memory persistent settings (_db_config) to the database.
        """
        if not self._system_config_repo:
            logger.error("SystemConfigRepository not available. Cannot save settings.")
            return False

        logger.info(
            f"Attempting to save {len(self._db_config)} persistent settings to database."
        )
        all_successful = True
        try:
            # Save each setting individually using the repository's set method
            for key, value in self._db_config.items():
                # Ensure value is converted to string for DB storage
                value_str = str(value) if value is not None else ""
                success = self._system_config_repo.set(key, value_str)
                if not success:
                    all_successful = False
                    logger.error(f"Failed to save setting '{key}' to database.")

            if all_successful:
                logger.info("Successfully saved persistent settings to database.")
            else:
                logger.warning(
                    "Failed to save one or more persistent settings to database."
                )
            return all_successful
        except Exception as e:
            logger.exception(
                "Error saving persistent settings to database", exc_info=True
            )
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value, checking sources in priority order:
        1. Environment Variables
        2. Database (in-memory cache _db_config)
        3. Default value from DEFAULT_PERSISTENT_CONFIG (if key exists there)
        4. Provided 'default' argument
        """
        # 1. Environment Variables (Highest Priority)
        env_value = os.environ.get(key)
        if env_value is not None:
            logger.debug(f"Config: Found '{key}' in environment variables.")
            # Attempt type conversion based on DEFAULT_PERSISTENT_CONFIG if possible
            if key in self.DEFAULT_PERSISTENT_CONFIG:
                _, expected_type = self.DEFAULT_PERSISTENT_CONFIG[key]
                try:
                    if expected_type == bool:
                        return env_value.lower() in ("true", "1", "yes")
                    return expected_type(env_value)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Could not convert env var '{key}' value '{env_value}' to {expected_type}. Using string."
                    )
                    return env_value
            return env_value  # Return as string if not a known persistent type

        # 2. Database (In-memory Cache)
        if key in self._db_config:
            logger.debug(f"Config: Found '{key}' in database cache.")
            return self._db_config[
                key
            ]  # Value is already typed correctly from _load_from_database

        # 3. Default Persistent Config Value
        if key in self.DEFAULT_PERSISTENT_CONFIG:
            default_persistent_value, _ = self.DEFAULT_PERSISTENT_CONFIG[key]
            logger.debug(f"Config: Using default persistent value for '{key}'.")
            return default_persistent_value

        # 4. Provided Default Argument
        logger.debug(f"Config: Key '{key}' not found. Returning provided default.")
        return default

    def get_persistent(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value specifically intended to be persistent.
        Priority: Environment -> Database Cache -> Default Persistent Value -> Provided Default.
        """
        # This method essentially becomes an alias for get() with the current logic,
        # as get() already prioritizes correctly and handles types for known persistent keys.
        return self.get(key, default)

    def set_persistent(self, key: str, value: Any):
        """
        Set a persistent configuration value in memory.
        Raises ValueError if the key is not defined in DEFAULT_PERSISTENT_CONFIG.
        Call save_persistent() explicitly to save changes to the database.
        """
        if key not in self.DEFAULT_PERSISTENT_CONFIG:
            raise ValueError(
                f"Cannot set '{key}': Not defined as a persistent setting."
            )

        _, expected_type = self.DEFAULT_PERSISTENT_CONFIG[key]
        try:
            # Attempt to cast value to expected type before storing in memory
            if expected_type == bool:
                typed_value = bool(value)
            elif expected_type == int:
                typed_value = int(value)
            elif expected_type == float:
                typed_value = float(value)
            else:
                typed_value = str(value)  # Default to string if type is str or unknown

            self._db_config[key] = typed_value
            logger.debug(
                f"Set persistent setting '{key}' to '{typed_value}' (type: {type(typed_value)}) in memory."
            )

        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to set persistent key '{key}': Value '{value}' could not be converted to {expected_type}. Error: {e}"
            )
            # Optionally raise an error here instead of just logging
            # raise TypeError(f"Invalid type for persistent setting '{key}'. Expected {expected_type}, got {type(value)}.")

    def reset_persistent_to_defaults(self) -> bool:
        """
        Reset all persistent settings IN MEMORY to their defaults.
        Also clears them from the database and saves the defaults back.
        Returns True if saving defaults to DB was successful, False otherwise.
        """
        logger.info("Resetting persistent settings to defaults...")
        self._db_config = {
            key: default_value
            for key, (default_value, _) in self.DEFAULT_PERSISTENT_CONFIG.items()
            if default_value is not None  # Only store non-None defaults
        }
        logger.info("Reset persistent settings in memory to defaults.")

        # Clear existing settings from the database first
        if self._system_config_repo:
            logger.warning(
                "Clearing all system configuration settings from database..."
            )
            cleared = self._system_config_repo.clear_all()
            if not cleared:
                logger.error(
                    "Failed to clear existing settings from database during reset. Proceeding to save defaults anyway."
                )
            # Save the current (default) in-memory settings back to the DB
            return self.save_persistent()
        else:
            logger.error(
                "Cannot reset database settings: SystemConfigRepository not available."
            )
            return False

    @property
    def data_dir(self) -> str:
        """Get the data storage directory path"""
        return self._data_dir

    @property
    def db_path(self) -> str:
        """Get the full path of the SQLite database"""
        return self._db_path


# Create a single, globally accessible instance of AppConfig
# The database repository will be set later during application startup
config = AppConfig()
