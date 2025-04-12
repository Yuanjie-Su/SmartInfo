# backend/services/setting_service.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service module
Responsible for managing application settings and API keys
"""

import logging
import json
from typing import Optional, Dict, Any, List, Tuple

from backend.config import (
    API_KEY_VOLCENGINE,
    AppConfig,
    API_KEY_DEEPSEEK,
    CONFIG_KEY_DATA_DIR,
    CONFIG_KEY_FETCH_FREQUENCY,
    CONFIG_KEY_UI_THEME,
    CONFIG_KEY_LANGUAGE,
)
from backend.db.repositories import ApiKeyRepository, SystemConfigRepository
# Import LLMClient if needed for connection tests
# from backend.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SettingService:
    """Service class for managing settings and API keys"""

    def __init__(
        self,
        config: AppConfig,
        api_key_repo: ApiKeyRepository,
        system_config_repo: SystemConfigRepository,
        # llm_client: Optional[LLMClient] = None # Optional: Pass if needed for tests
    ):
        self._config = config
        self._api_key_repo = api_key_repo
        self._system_config_repo = system_config_repo
        # self._llm_client = llm_client

    # --- API Key Management ---

    def get_api_key(self, api_name: str) -> Optional[str]:
        """
        Get API key value. Prioritizes environment variables (via config), then the database.
        """
        # 1. Check environment variables via config
        env_key_name = None
        if api_name.lower() == "deepseek":
            env_key_name = API_KEY_DEEPSEEK
        elif api_name.lower() == "volcengine":
            env_key_name = API_KEY_VOLCENGINE
        # Add more mappings here if needed

        if env_key_name:
            env_key_value = self._config.get(env_key_name)
            if env_key_value:
                logger.debug(f"Using {api_name} API key from environment.")
                return env_key_value

        # 2. Fallback to database
        logger.debug(
            f"API key for '{api_name}' not found in environment, checking database."
        )
        try:
            return self._api_key_repo.get_key(api_name)
        except Exception as e:
            logger.error(f"Error fetching API key '{api_name}' from DB: {e}", exc_info=True)
            return None

    async def save_api_key(self, api_name: str, api_key: str) -> bool:
        """
        Save API key to the database.
        Note: Environment variables will still be prioritized during retrieval.
        """
        if not api_name or not api_key:
            logger.error("Cannot save API key: api_name and api_key cannot be empty.")
            return False
        logger.info(f"Saving API key for '{api_name}' to database.")
        try:
            return self._api_key_repo.save_key(api_name, api_key)
        except Exception as e:
            logger.error(f"Error saving API key '{api_name}' to DB: {e}", exc_info=True)
            return False

    async def delete_api_key_from_db(self, api_name: str) -> bool:
        """Delete API key from the database."""
        logger.info(f"Deleting API key for '{api_name}' from database.")
        try:
            return self._api_key_repo.delete_key(api_name)
        except Exception as e:
             logger.error(f"Error deleting API key '{api_name}' from DB: {e}", exc_info=True)
             return False

    async def list_api_keys_info(self) -> List[Dict[str, str]]:
        """
        Get information of all API keys stored in the database
        (name, creation date, modification date).
        Returns a list of dictionaries suitable for API responses.
        """
        try:
            keys_info = self._api_key_repo.get_all_keys_info() # Returns List[Tuple[str, str, str]]
            # Map tuple to dictionary
            return [
                {"api_name": name, "created_date": created, "modified_date": modified}
                for name, created, modified in keys_info
            ]
        except Exception as e:
            logger.error(f"Error listing API keys info from DB: {e}", exc_info=True)
            return []

    # --- System Settings Management ---

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get persistent system setting value from AppConfig."""
        # AppConfig handles loading from DB/defaults
        return self._config.get_persistent(key, default)

    async def save_setting(self, key: str, value: Any) -> bool:
        """Save persistent system setting (in memory and database via AppConfig)."""
        # Check if the key is a valid persistent config key
        if key not in self._config.DEFAULT_PERSISTENT_CONFIG:
             logger.warning(f"Attempted to save unknown or non-persistent config key: {key}")
             # Optionally return False or raise an error, depending on desired strictness
             # For flexibility, allow saving but log a warning. AppConfig might ignore it.
             # return False

        # Let AppConfig handle type validation and saving
        try:
            self._config.set_persistent(key, value)
            return self._config.save_persistent() # This saves *all* persistent settings
        except Exception as e:
             logger.error(f"Error saving setting '{key}': {e}", exc_info=True)
             return False

    async def get_all_settings(self) -> Dict[str, Any]:
        """Get all current persistent system settings (from AppConfig memory)."""
        # Return a copy to prevent external modification of the internal state
        return self._config._persistent_config.copy()

    async def delete_setting(self, key: str) -> bool:
        """Deletes a setting from the database and resets it to default in memory."""
        # 1. Check if it's a default persistent key
        if key not in self._config.DEFAULT_PERSISTENT_CONFIG:
            logger.warning(f"Attempted to delete non-standard or non-persistent config key: {key}")
            # Decide if we should attempt DB deletion anyway or just return False
            # Let's try DB deletion for cleanup but maintain the warning.
            # return False # Stricter approach

        # 2. Delete from DB using the repository
        deleted_from_db = False
        try:
            deleted_from_db = self._system_config_repo.delete_config(key)
            if not deleted_from_db:
                 logger.warning(f"System config key '{key}' not found in database for deletion.")
                 # If it wasn't in DB, we might still want to reset memory below.
        except Exception as e:
            logger.error(f"Error deleting setting '{key}' from DB: {e}", exc_info=True)
            return False # Return failure if DB operation failed

        # 3. Reset the key in memory to its default value
        if key in self._config.DEFAULT_PERSISTENT_CONFIG:
            default_value = self._config.DEFAULT_PERSISTENT_CONFIG[key]
            self._config.set_persistent(key, default_value) # Reset in memory
            logger.info(f"Reset setting '{key}' to its default value in memory.")
            # No need to call save_persistent() here as we just deleted it from DB
            # If the goal was ONLY to remove from DB, skip step 3.
            # If the goal is reset-to-default, step 3 is needed. Assuming reset is desired.
            # We might need to save *other* pending changes if any exist.
            # self._config.save_persistent() # Uncomment if other changes might need saving

        return True # Report success even if key wasn't in DB but memory was reset


    async def reset_settings_to_defaults(self) -> bool:
        """Reset persistent settings to default values (in memory and database)."""
        # 1. Reset in memory using AppConfig method
        self._config.reset_persistent_to_defaults()
        # 2. Clear *all* settings from DB
        try:
            cleared_db = self._system_config_repo.delete_all()
            if not cleared_db:
                 logger.warning("System config table might already be empty or deletion failed.")
                 # Continue to save defaults anyway
        except Exception as e:
            logger.error(f"Error clearing system config from DB during reset: {e}", exc_info=True)
            return False # Fail if DB clear failed critically

        # 3. Save the current (default) settings from memory back to the DB
        return self._config.save_persistent()


    # --- Specific Setting Getters/Setters (Convenience examples) ---

    async def get_data_dir(self) -> str:
        return self._config.data_dir

    async def get_fetch_frequency(self) -> str:
        default = AppConfig.DEFAULT_PERSISTENT_CONFIG.get(CONFIG_KEY_FETCH_FREQUENCY, "manual")
        return await self.get_setting(CONFIG_KEY_FETCH_FREQUENCY, default)

    async def save_fetch_frequency(self, frequency: str) -> bool:
        # Add validation for frequency value if needed
        return await self.save_setting(CONFIG_KEY_FETCH_FREQUENCY, frequency)