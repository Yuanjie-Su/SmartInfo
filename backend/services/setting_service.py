#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service for managing application settings and API keys
"""

import logging
import json
from typing import Dict, Any, List, Optional, Union

# Import using backend package path
from config import AppConfig
from db.repositories.api_key_repository import ApiKeyRepository
from db.repositories.system_config_repository import SystemConfigRepository
from models.schemas.api_key import ApiKey
from core.llm.client import AsyncLLMClient

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

    async def get_api_key_by_id(self, api_id: int) -> Optional[ApiKey]:
        """Get an ApiKey object by ID"""
        # 使用返回Record的方法
        api_key_record = await self._api_key_repo.get_by_id(api_id)
        if not api_key_record:
            return None

        # 将Record转换为字典，然后创建ApiKey对象
        api_key_dict = dict(api_key_record)
        return ApiKey(**api_key_dict)

    async def get_all_api_keys(self) -> List[ApiKey]:
        """Get all API keys"""
        api_keys_data = await self._api_key_repo.get_all()
        return [
            ApiKey(
                id=item["id"],
                model=item["model"],
                base_url=item["base_url"],
                api_key=item["api_key"],
                context=item["context"],
                max_output_tokens=item["max_output_tokens"],
                description=item.get("description"),
                created_date=item.get("created_date"),
                modified_date=item.get("modified_date"),
            )
            for item in api_keys_data
        ]

    async def save_api_key(
        self,
        model: str,
        base_url: str,
        api_key: str,
        context: int,
        max_output_tokens: int,
        description: Optional[str] = None,
    ) -> ApiKey:
        """Save a new API key"""
        if not model or not base_url or not api_key:
            raise ValueError("Model, base URL, and API key are required")

        if not isinstance(context, int) or not isinstance(max_output_tokens, int):
            raise ValueError("Context and max output tokens must be integers")

        if context <= max_output_tokens:
            raise ValueError("Context must be greater than max output tokens")

        # Create new key
        key_id = await self._api_key_repo.add(
            model=model,
            base_url=base_url,
            api_key=api_key,
            context=context,
            max_output_tokens=max_output_tokens,
            description=description,
        )

        if key_id:
            return await self.get_api_key_by_id(key_id)

        raise ValueError(f"Failed to save API key for {model}")

    async def update_api_key(
        self,
        api_id: int,
        model: str,
        base_url: str,
        context: int,
        max_output_tokens: int,
        api_key: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[ApiKey]:
        """Update an existing API key"""
        if not model or not base_url:
            raise ValueError("Model and base URL are required")

        if not isinstance(context, int) or not isinstance(max_output_tokens, int):
            raise ValueError("Context and max output tokens must be integers")

        if context <= max_output_tokens:
            raise ValueError("Context must be greater than max output tokens")

        # Check if API key exists by ID
        existing_key = await self._api_key_repo.get_by_id(api_id)
        if not existing_key:
            return None

        # Use the update method by ID
        updated = await self._api_key_repo.update(
            api_id=api_id,
            model=model,
            base_url=base_url,
            api_key=api_key,
            context=context,
            max_output_tokens=max_output_tokens,
            description=description,
        )

        if not updated:
            return None

        return await self.get_api_key_by_id(api_id)

    async def delete_api_key(self, api_id: int) -> bool:
        """Delete an API key by ID"""
        return await self._api_key_repo.delete(api_id)

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

    async def test_api_key_connection(self, api_key_id: int) -> Dict[str, Any]:
        """
        Test connection for a specific API key by ID.

        Args:
            api_key_id: ID of the API key to test

        Returns:
            Dictionary with test status and results

        Raises:
            HTTPException: If the API key is not found
        """
        # 使用返回Record的方法
        api_key_record = await self._api_key_repo.get_by_id(api_key_id)
        if not api_key_record:
            # We'll let the router convert this to a 404 HTTP response
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID '{api_key_id}' not found.",
            )

        # 将Record转换为字典
        api_key_dict = dict(api_key_record)

        # Extract relevant information from the dictionary
        model = api_key_dict["model"]
        base_url = api_key_dict["base_url"]
        api_key = api_key_dict["api_key"]
        max_output_tokens = api_key_dict["max_output_tokens"]

        # Create a simple test message
        test_messages = [{"role": "user", "content": "hello"}]

        # Create a temporary LLM client for testing
        try:
            async with AsyncLLMClient(
                base_url=base_url,
                api_key=api_key,
                timeout=10,  # Use a shorter timeout for testing
            ) as client:
                # Call the client with minimal tokens for a faster test
                response_content = await client.get_completion_content(
                    messages=test_messages,
                    model=model,
                    max_tokens=min(
                        10, max_output_tokens
                    ),  # Use a small max_tokens value
                    temperature=0.7,
                )

                # Check the response
                if response_content:
                    return {
                        "status": "success",
                        "message": "Connection successful",
                        "response_snippet": (
                            f"{response_content[:50]}..."
                            if len(response_content) > 50
                            else response_content
                        ),
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Connection test failed: No response received",
                    }

        except Exception as e:
            logger.error(f"API key test failed for ID {api_key_id}: {str(e)}")
            return {"status": "error", "message": f"Connection test failed: {str(e)}"}
