# backend/services/setting_service.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service module (Async DB)
Responsible for managing application settings and API keys
"""

import logging
import json
from typing import Optional, Dict, Any, List, Tuple
import httpx # Changed from requests
import time
import asyncio # Added for potential sleep/retry

from backend.config import (
    API_KEY_VOLCENGINE,
    AppConfig,
    API_KEY_DEEPSEEK,
    # ... other config keys
)
from backend.db.repositories import ApiKeyRepository, SystemConfigRepository

logger = logging.getLogger(__name__)


class SettingService:
    """Service class for managing settings and API keys (Async DB)"""

    def __init__(
        self,
        config: AppConfig,
        api_key_repo: ApiKeyRepository,
        system_config_repo: SystemConfigRepository,
    ):
        self._config = config
        self._api_key_repo = api_key_repo
        self._system_config_repo = system_config_repo

    # --- API Key Management ---

    async def get_api_key(self, api_name: str) -> Optional[str]: # Changed to async def
        """
        Get API key value asynchronously. Prioritizes environment variables, then the database.
        """
        # 1. Check environment variables via config (sync)
        env_key_name = None
        if api_name.lower() == "deepseek":
            env_key_name = API_KEY_DEEPSEEK
        elif api_name.lower() == "volcengine":
            env_key_name = API_KEY_VOLCENGINE

        if env_key_name:
            env_key_value = self._config.get(env_key_name) # Config access is sync
            if env_key_value:
                logger.debug(f"Using {api_name} API key from environment.")
                return env_key_value

        # 2. Fallback to database (async)
        logger.debug(
            f"API key for '{api_name}' not found in environment, checking database."
        )
        try:
            return await self._api_key_repo.get_key(api_name) # Added await
        except Exception as e:
            logger.error(f"Error fetching API key '{api_name}' from DB: {e}", exc_info=True)
            return None

    async def save_api_key(self, api_name: str, api_key: str) -> bool:
        """Save API key to the database asynchronously."""
        if not api_name or not api_key:
            logger.error("Cannot save API key: api_name and api_key cannot be empty.")
            return False
        logger.info(f"Saving API key for '{api_name}' to database.")
        try:
            return await self._api_key_repo.save_key(api_name, api_key) # Added await
        except Exception as e:
            logger.error(f"Error saving API key '{api_name}' to DB: {e}", exc_info=True)
            return False

    async def delete_api_key_from_db(self, api_name: str) -> bool:
        """Delete API key from the database asynchronously."""
        logger.info(f"Deleting API key for '{api_name}' from database.")
        try:
            return await self._api_key_repo.delete_key(api_name) # Added await
        except Exception as e:
             logger.error(f"Error deleting API key '{api_name}' from DB: {e}", exc_info=True)
             return False

    async def list_api_keys_info(self) -> List[Dict[str, str]]:
        """Get info of all API keys stored in the database asynchronously."""
        try:
            keys_info = await self._api_key_repo.get_all_keys_info() # Added await
            return [
                {"api_name": name, "created_date": created, "modified_date": modified}
                for name, created, modified in keys_info
            ]
        except Exception as e:
            logger.error(f"Error listing API keys info from DB: {e}", exc_info=True)
            return []

    # --- System Settings Management ---

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get persistent system setting value from AppConfig (sync)."""
        # AppConfig access is synchronous
        return self._config.get_persistent(key, default)

    async def save_setting(self, key: str, value: Any) -> bool:
        """Save persistent system setting (in memory sync, DB async via AppConfig)."""
        if key not in self._config.DEFAULT_PERSISTENT_CONFIG:
             logger.warning(f"Attempted to save unknown or non-persistent config key: {key}")
             # return False # Or allow saving if AppConfig handles unknown keys gracefully

        try:
            # Set in memory (sync)
            self._config.set_persistent(key, value)
            # Save all persistent settings to DB (async)
            return await self._config.save_persistent() # Changed to await
        except Exception as e:
             logger.error(f"Error saving setting '{key}': {e}", exc_info=True)
             return False

    def get_all_settings(self) -> Dict[str, Any]: # Changed to sync def
        """Get all current persistent system settings (from AppConfig memory - sync)."""
        return self._config._persistent_config.copy()

    async def delete_setting(self, key: str) -> bool:
        """Deletes a setting from the database (async) and resets it to default in memory (sync)."""
        if key not in self._config.DEFAULT_PERSISTENT_CONFIG:
            logger.warning(f"Attempted to delete non-standard or non-persistent config key: {key}")
            # Optionally return False

        deleted_from_db = False
        try:
            # Delete from DB async
            deleted_from_db = await self._system_config_repo.delete_config(key) # Added await
            if not deleted_from_db:
                 logger.warning(f"System config key '{key}' not found in database for deletion.")
        except Exception as e:
            logger.error(f"Error deleting setting '{key}' from DB: {e}", exc_info=True)
            return False # Return failure if DB operation failed

        # Reset the key in memory to its default value (sync)
        if key in self._config.DEFAULT_PERSISTENT_CONFIG:
            default_value = self._config.DEFAULT_PERSISTENT_CONFIG[key]
            self._config.set_persistent(key, default_value)
            logger.info(f"Reset setting '{key}' to its default value in memory.")

        return True

    async def reset_settings_to_defaults(self) -> bool:
        """Reset persistent settings to default values (memory sync, DB async)."""
        # 1. Reset in memory (sync)
        self._config.reset_persistent_to_defaults()
        # 2. Clear *all* settings from DB (async)
        try:
            cleared_db = await self._system_config_repo.delete_all() # Added await
            if not cleared_db:
                 logger.warning("System config table might already be empty or deletion failed.")
        except Exception as e:
            logger.error(f"Error clearing system config from DB during reset: {e}", exc_info=True)
            return False

        # 3. Save the current (default) settings from memory back to the DB (async)
        return await self._config.save_persistent() # Added await


    # --- Specific Setting Getters/Setters ---
    # These typically just wrap get_setting/save_setting

    def get_data_dir(self) -> str: # Changed to sync
        """Gets data directory (sync access to config)."""
        return self._config.data_dir

    async def get_fetch_frequency(self) -> str:
        """Gets fetch frequency setting (async due to get_setting)."""
        default = AppConfig.DEFAULT_PERSISTENT_CONFIG.get(CONFIG_KEY_FETCH_FREQUENCY, "manual")
        # get_setting is sync, but keep this async for consistency if needed later
        return await self.get_setting(CONFIG_KEY_FETCH_FREQUENCY, default) # get_setting itself is sync now

    async def save_fetch_frequency(self, frequency: str) -> bool:
         """Saves fetch frequency setting (async due to save_setting)."""
         return await self.save_setting(CONFIG_KEY_FETCH_FREQUENCY, frequency) # Calls async save_setting