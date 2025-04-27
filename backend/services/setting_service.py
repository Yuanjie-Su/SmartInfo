#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service for managing application settings and API keys
"""

import logging
import json
from typing import Dict, Any, List, Optional, Union

# Import using backend package path
from backend.config import AppConfig
from backend.db.repositories.api_key_repository import ApiKeyRepository
from backend.db.repositories.system_config_repository import SystemConfigRepository
from backend.models.schemas.api_key import ApiKey

logger = logging.getLogger(__name__)


class SettingService:
    """Service for managing application settings and API keys"""

    def __init__(
        self,
        config: AppConfig,
        api_key_repo: ApiKeyRepository,
        system_config_repo: SystemConfigRepository,
    ):
        """Initialize the setting service"""
        self._config = config
        self._api_key_repo = api_key_repo
        self._system_config_repo = system_config_repo

    async def get_api_key(self, api_name: str) -> Optional[str]:
        """Get an API key by name (prioritize env vars, then DB)"""
        # First try from environment variables via config
        api_key_value = None
        if api_name.lower() == "deepseek":
            api_key_value = self._config.get("API_KEY_DEEPSEEK")
        elif api_name.lower() == "volcengine":
            api_key_value = self._config.get("LLM_API_KEY")

        # If not found in env vars, try from database
        if not api_key_value:
            api_key_tuple = await self._api_key_repo.get_by_name(api_name)
            if api_key_tuple:
                api_key_value = api_key_tuple[2]  # index 2 contains the API key

        return api_key_value

    async def get_api_key_by_name(self, api_name: str) -> Optional[ApiKey]:
        """Get an ApiKey object by name"""
        api_key_tuple = await self._api_key_repo.get_by_name(api_name)
        if not api_key_tuple:
            return None

        # Convert tuple to ApiKey and convert timestamps to strings
        # Assuming timestamps are stored as integers and need conversion for the schema
        created_date = api_key_tuple[4]
        modified_date = api_key_tuple[5]

        return ApiKey(
            id=api_key_tuple[0],
            api_name=api_key_tuple[1],
            api_key=api_key_tuple[2],
            description=api_key_tuple[3],
            created_date=created_date,
            modified_date=modified_date,
        )

    async def get_all_api_keys(self) -> List[ApiKey]:
        """Get all API keys"""
        api_keys_data = await self._api_key_repo.get_all()
        return [
            ApiKey(
                id=item["id"],
                api_name=item["api_name"],
                api_key=item["api_key"],
                description=item.get("description"),
                created_date=item.get("created_date"),
                modified_date=item.get("modified_date"),
            )
            for item in api_keys_data
        ]

    async def save_api_key(
        self, api_name: str, api_key: str, description: Optional[str] = None
    ) -> ApiKey:
        """Save an API key (create or update)"""
        if not api_name or not api_key:
            raise ValueError("API name and key are required")

        # Check if API key exists by name
        existing_key = await self._api_key_repo.get_by_name(api_name)

        if existing_key:
            # Update existing key using the update method by ID
            updated = await self._api_key_repo.update(
                existing_key[0], api_key, description
            )
            if updated:
                return await self.get_api_key_by_name(api_name)
        else:
            # Create new key using the add method
            key_id = await self._api_key_repo.add(api_name, api_key, description)
            if key_id:
                return await self.get_api_key_by_name(api_name)

        raise ValueError(f"Failed to save API key for {api_name}")

    async def update_api_key(
        self, api_name: str, api_key: str, description: Optional[str] = None
    ) -> Optional[ApiKey]:
        """Update an existing API key"""
        if not api_name or not api_key:
            raise ValueError("API name and key are required")

        # Check if API key exists by name
        existing_key = await self._api_key_repo.get_by_name(api_name)
        if not existing_key:
            return None

        # Use the update method by ID
        updated = await self._api_key_repo.update(existing_key[0], api_key, description)
        if not updated:
            return None

        return await self.get_api_key_by_name(api_name)

    async def delete_api_key(self, api_name: str) -> bool:
        """Delete an API key"""
        existing_key = await self._api_key_repo.get_by_name(api_name)
        if not existing_key:
            return False

        return await self._api_key_repo.delete(existing_key[0])

    async def get_all_settings(self) -> Dict[str, Any]:
        """Get all application settings"""
        # Get settings from config (persistent settings loaded from DB and environment)
        settings = {}
        # Get persistent settings from the config object (already loaded from DB)
        for key in self._config.DEFAULT_PERSISTENT_CONFIG:
            settings[key] = self._config.get_persistent(key)

        return settings

    async def update_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update application settings"""
        if not settings:
            return await self.get_all_settings()

        # Validate settings keys against the default persistent config keys
        valid_keys = self._config.DEFAULT_PERSISTENT_CONFIG.keys()
        invalid_keys = [k for k in settings if k not in valid_keys]
        if invalid_keys:
            raise ValueError(f"Invalid settings keys: {', '.join(invalid_keys)}")

        # Update settings in config's in-memory representation
        for key, value in settings.items():
            self._config.set_persistent(key, value)

        # Save the updated persistent settings from memory to the database
        success = await self._config.save_persistent()
        if not success:
            raise RuntimeError("Failed to save settings to database")

        return await self.get_all_settings()

    async def reset_settings_to_defaults(self) -> Dict[str, Any]:
        """Reset application settings to defaults"""
        # Reset settings in config's in-memory representation to defaults
        self._config.reset_persistent_to_defaults()

        # Clear existing settings from the database and save the default settings
        success = await self._system_config_repo.clear_all()  # Clear existing from DB

        if not success:
            logger.error("Failed to clear existing system config from DB during reset.")
            # Continue to save defaults even if clearing old settings failed
            # raise RuntimeError("Failed to clear existing system config from database")

        # Save the default settings from memory to the database
        success = await self._config.save_persistent()
        if not success:
            raise RuntimeError("Failed to save default settings to database")

        return await self.get_all_settings()
