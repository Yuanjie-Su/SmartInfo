#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service module
Responsible for managing application settings and API keys
"""

import logging
import json
from typing import Optional, Dict, Any, List, Tuple

from src.config import (
    API_KEY_VOLCENGINE,
    AppConfig,
    API_KEY_DEEPSEEK,
    CONFIG_KEY_DATA_DIR,
    CONFIG_KEY_FETCH_FREQUENCY,
    CONFIG_KEY_UI_THEME,
    CONFIG_KEY_LANGUAGE,
)
from src.db.repositories import ApiKeyRepository, SystemConfigRepository

logger = logging.getLogger(__name__)


class SettingService:
    """Service class for managing settings and API keys"""

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

    def get_api_key(self, api_name: str) -> Optional[str]:
        """
        Get API key. Preferably from environment variables (via config), then from the database.
        """
        # 1. Check environment variables via config
        if api_name.lower() == "deepseek":
            env_key = self._config.get(API_KEY_DEEPSEEK)
            if env_key:
                logger.debug(f"Using DeepSeek API key from environment.")
                return env_key
        
        if api_name.lower() == "volcengine":
            env_key = self._config.get(API_KEY_VOLCENGINE)
            if env_key:
                logger.debug(f"Using Volcano Engine API key from environment.")
                return env_key

        # 2. Fallback to database
        logger.debug(
            f"API key for '{api_name}' not found in environment, checking database."
        )
        return self._api_key_repo.get_key(api_name)

    def save_api_key(self, api_name: str, api_key: str) -> bool:
        """
        Save API key to the database.
        Note: This will not overwrite the value in environment variables.
        When retrieving, environment variables will still be prioritized.
        """
        # Basic validation
        if not api_name or not api_key:
            logger.error("Cannot save API key: api_name and api_key cannot be empty.")
            return False
        logger.info(f"Saving API key for '{api_name}' to database.")
        return self._api_key_repo.save_key(api_name, api_key)

    def delete_api_key_from_db(self, api_name: str) -> bool:
        """Delete API key from the database."""
        logger.info(f"Deleting API key for '{api_name}' from database.")
        return self._api_key_repo.delete_key(api_name)

    def list_api_keys_info(self) -> List[Tuple[str, str, str]]:
        """Get information of all API keys in the database (name, creation date, modification date)."""
        return self._api_key_repo.get_all_keys_info()

    def test_deepseek_connection(self, api_key: str) -> Dict[str, Any]:
        """
        Test DeepSeek API connection (using the provided key).
        (This was originally in utils/api_client.py)
        """
        # Ideally, this would use the main LLMClient for consistency,
        # but since it's a specific connection test with potentially
        # unsaved keys, using requests might be acceptable here.
        # Or, instantiate a temporary LLMClient. Let's use requests for now.
        import requests
        import time

        url = "https://api.deepseek.com/chat/completions"  # Use the correct DeepSeek API endpoint
        payload = json.dumps(
            {
                "messages": [{"role": "user", "content": "Hello!"}],
                "model": "deepseek-chat",  # Use a valid model name
                "max_tokens": 2,
                "temperature": 0,
                "stream": True,  # Use stream to quickly check connection
            }
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        start_time = time.time()
        try:
            # Use stream=True with requests and timeout
            with requests.post(
                url, headers=headers, data=payload, stream=True, timeout=15
            ) as response:
                if response.status_code == 200:
                    # Check if we receive *any* data chunk
                    for chunk in response.iter_content(
                        chunk_size=10
                    ):  # Read small chunks
                        if chunk:
                            latency = round(time.time() - start_time, 2)
                            logger.info(
                                f"DeepSeek connection test successful (latency: {latency}s)."
                            )
                            return {
                                "success": True,
                                "response": "Connection successful",
                                "latency": latency,
                            }
                    # If loop finishes without chunks, something is wrong
                    logger.warning(
                        "DeepSeek connection test: Status 200 but no data received."
                    )
                    return {
                        "success": False,
                        "error": "Connection successful but no data stream received",
                    }
                else:
                    error_msg = (
                        f"API request failed, status code: {response.status_code}"
                    )
                    try:
                        error_details = response.json()  # Try to get error details
                        error_msg += f", details: {error_details}"
                    except json.JSONDecodeError:
                        error_msg += f", response content: {response.text[:200]}"  # Show partial raw response
                    logger.error(f"DeepSeek connection test failed: {error_msg}")
                    return {"success": False, "error": error_msg}

        except requests.exceptions.RequestException as e:
            logger.error(
                f"DeepSeek connection test failed (RequestException): {str(e)}",
                exc_info=True,
            )
            return {"success": False, "error": f"Network or request error: {str(e)}"}
        except Exception as e:
            logger.error(
                f"DeepSeek connection test failed (Unknown error): {str(e)}",
                exc_info=True,
            )
            return {"success": False, "error": f"Unknown error: {str(e)}"}

    # --- System Settings Management ---

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get persistent system settings"""
        # Retrieve from the AppConfig instance, which already loaded from DB
        return self._config.get_persistent(key, default)

    def save_setting(self, key: str, value: Any) -> bool:
        """Save persistent system settings (in memory and database)"""
        # 1. Update in memory
        self._config.set_persistent(key, value)
        # 2. Persist all changes to DB
        return (
            self._config.save_persistent()
        )  # save_persistent saves all keys in memory

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all current persistent settings (from memory)"""
        # Return a copy to prevent modification
        return (
            self._config._persistent_config.copy()
        )  # Access internal dict for snapshot

    def reset_settings_to_defaults(self) -> bool:
        """Reset persistent settings to default values (in memory and database)"""
        # 1. Reset in memory
        self._config.reset_persistent_to_defaults()
        # 2. Clear from DB and save defaults
        # We need to clear first, then save the defaults from memory
        if self._system_config_repo.delete_all():
            return self._config.save_persistent()
        else:
            logger.error("Failed to clear existing system config from DB during reset.")
            return False

    # --- Specific Setting Getters/Setters (Convenience) ---

    def get_data_dir(self) -> str:
        return self._config.data_dir

    def get_fetch_frequency(self) -> str:
        default = AppConfig.DEFAULT_PERSISTENT_CONFIG[CONFIG_KEY_FETCH_FREQUENCY]
        return self.get_setting(CONFIG_KEY_FETCH_FREQUENCY, default)

    def save_fetch_frequency(self, frequency: str) -> bool:
        return self.save_setting(CONFIG_KEY_FETCH_FREQUENCY, frequency)
