#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service for managing user-specific application settings and API keys
"""

import logging
import json
from typing import Dict, Any, List, Optional, Union

# Import using backend package path
from config import AppConfig  # Keep for default values, but user settings override
from db.repositories.api_key_repository import ApiKeyRepository
from db.repositories.system_config_repository import SystemConfigRepository
from models import (
    ApiKey,
    ApiKeyCreate,
    SystemConfig,
    SystemConfigBase,
    User,
)  # Import relevant models

from core.llm.client import AsyncLLMClient

logger = logging.getLogger(__name__)


class SettingService:
    """Service for managing user-specific application settings and API keys"""

    def __init__(
        self,
        config: AppConfig,  # Keep config for defaults
        api_key_repo: ApiKeyRepository,
        system_config_repo: SystemConfigRepository,
    ):
        """Initialize the setting service"""
        self._config = config  # Used for default values
        self._api_key_repo = api_key_repo
        self._system_config_repo = system_config_repo

    # --- API Key Management (User-Aware) ---

    async def get_api_key_by_id(self, api_id: int, user_id: int) -> Optional[ApiKey]:
        """Get an ApiKey object by ID for a specific user."""
        api_key_record = await self._api_key_repo.get_by_id(api_id, user_id)
        if not api_key_record:
            return None
        # Assuming ApiKey model includes user_id
        return ApiKey.model_validate(api_key_record)  # Use model_validate

    async def get_all_api_keys(self, user_id: int) -> List[ApiKey]:
        """Get all API keys for a specific user."""
        api_keys_data = await self._api_key_repo.get_all(user_id)
        # Assuming ApiKey model includes user_id
        return [
            ApiKey.model_validate(item) for item in api_keys_data
        ]  # Use model_validate

    async def save_api_key(
        self, api_key_data: ApiKeyCreate, user_id: int  # Use Pydantic model
    ) -> ApiKey:
        """Save a new API key for a specific user."""
        if api_key_data.user_id != user_id:
            raise ValueError(
                "User ID in API key data does not match authenticated user."
            )

        if (
            not api_key_data.model
            or not api_key_data.base_url
            or not api_key_data.api_key
        ):
            raise ValueError("Model, base URL, and API key are required")

        if not isinstance(api_key_data.context, int) or not isinstance(
            api_key_data.max_output_tokens, int
        ):
            raise ValueError("Context and max output tokens must be integers")

        if api_key_data.context <= api_key_data.max_output_tokens:
            raise ValueError("Context must be greater than max output tokens")

        key_id = await self._api_key_repo.add(
            model=api_key_data.model,
            base_url=str(api_key_data.base_url),  # Ensure URL is string
            api_key=api_key_data.api_key,
            context=api_key_data.context,
            max_output_tokens=api_key_data.max_output_tokens,
            description=api_key_data.description,
            user_id=user_id,  # Pass user_id
        )

        if key_id:
            created_key = await self.get_api_key_by_id(key_id, user_id)
            if created_key:
                return created_key
            else:
                # Should not happen if add succeeded
                raise RuntimeError(
                    f"Failed to retrieve newly created API key {key_id} for user {user_id}"
                )

        raise ValueError(
            f"Failed to save API key for model {api_key_data.model} for user {user_id}"
        )

    async def update_api_key(
        self,
        api_id: int,
        user_id: int,  # Add user_id
        api_key_data: ApiKeyCreate,  # Use Pydantic model for update data
    ) -> Optional[ApiKey]:
        """Update an existing API key for a specific user."""
        if api_key_data.user_id != user_id:
            raise ValueError(
                "User ID in API key data does not match authenticated user."
            )

        if not api_key_data.model or not api_key_data.base_url:
            raise ValueError("Model and base URL are required")

        if not isinstance(api_key_data.context, int) or not isinstance(
            api_key_data.max_output_tokens, int
        ):
            raise ValueError("Context and max output tokens must be integers")

        if api_key_data.context <= api_key_data.max_output_tokens:
            raise ValueError("Context must be greater than max output tokens")

        # Repository update method checks ownership via user_id in WHERE clause
        updated = await self._api_key_repo.update(
            api_id=api_id,
            user_id=user_id,  # Pass user_id for ownership check
            model=api_key_data.model,
            base_url=str(api_key_data.base_url),
            api_key=api_key_data.api_key,  # Pass optional new key
            context=api_key_data.context,
            max_output_tokens=api_key_data.max_output_tokens,
            description=api_key_data.description,
        )

        if not updated:
            return None  # Update failed (likely not found or not owned)

        return await self.get_api_key_by_id(api_id, user_id)

    async def delete_api_key(self, api_id: int, user_id: int) -> bool:
        """Delete an API key by ID for a specific user."""
        return await self._api_key_repo.delete(api_id, user_id)

    # --- System Settings Management (User-Aware) ---

    async def get_all_settings(self, user_id: int) -> Dict[str, Any]:
        """Get all application settings for a specific user, falling back to defaults."""
        user_settings = await self._system_config_repo.get_all(user_id)

        # Combine user settings with defaults, user settings take precedence
        final_settings = {}
        for key, default_value in self._config.DEFAULT_PERSISTENT_CONFIG.items():
            final_settings[key] = user_settings.get(
                key, default_value
            )  # Use default if not set by user

        return final_settings

    async def update_settings(
        self, settings: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """Update application settings for a specific user."""
        if not settings:
            return await self.get_all_settings(user_id)

        valid_keys = self._config.DEFAULT_PERSISTENT_CONFIG.keys()
        invalid_keys = [k for k in settings if k not in valid_keys]
        if invalid_keys:
            raise ValueError(f"Invalid settings keys: {', '.join(invalid_keys)}")

        # Save each setting to the database for the user
        all_success = True
        for key, value in settings.items():
            # Convert value to string for storage if necessary (repo expects string)
            # Consider more robust type handling based on key if needed
            str_value = str(value)
            success = await self._system_config_repo.set(
                config_key=key,
                config_value=str_value,
                user_id=user_id,
                # Optionally fetch description from defaults or pass None
                description=self._config.DEFAULT_PERSISTENT_CONFIG_DESC.get(key),
            )
            if not success:
                all_success = False
                logger.error(f"Failed to save setting '{key}' for user {user_id}")
                # Decide whether to continue or raise immediately
                # raise RuntimeError(f"Failed to save setting '{key}' for user {user_id}")

        if not all_success:
            # Or raise a more general error if partial success is unacceptable
            logger.warning(f"One or more settings failed to save for user {user_id}")

        return await self.get_all_settings(user_id)

    async def reset_settings_to_defaults(self, user_id: int) -> Dict[str, Any]:
        """Reset application settings to defaults for a specific user."""
        # Clear existing settings for the user from the database
        success = await self._system_config_repo.clear_all_for_user(user_id)

        if not success:
            logger.error(
                f"Failed to clear existing system config from DB for user {user_id} during reset."
            )
            # Depending on requirements, might want to raise an error here
            # raise RuntimeError(f"Failed to clear existing system config for user {user_id}")

        # Return the default settings (as no user-specific settings exist now)
        default_settings = {}
        for key, default_value in self._config.DEFAULT_PERSISTENT_CONFIG.items():
            default_settings[key] = default_value
        return default_settings

    # --- API Key Testing (User-Aware) ---

    async def test_api_key_connection(
        self, api_key_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Test connection for a specific API key belonging to a user.
        """
        api_key_record = await self._api_key_repo.get_by_id(api_key_id, user_id)
        if not api_key_record:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID '{api_key_id}' not found or not owned by user.",
            )

        api_key_dict = dict(api_key_record)
        model = api_key_dict["model"]
        base_url = api_key_dict["base_url"]
        api_key = api_key_dict["api_key"]
        max_output_tokens = api_key_dict["max_output_tokens"]

        test_messages = [{"role": "user", "content": "hello"}]

        try:
            async with AsyncLLMClient(
                base_url=base_url,
                api_key=api_key,
                timeout=10,
            ) as client:
                response_content = await client.get_completion_content(
                    messages=test_messages,
                    model=model,
                    max_tokens=min(10, max_output_tokens),
                    temperature=0.7,
                )

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
            logger.error(
                f"API key test failed for ID {api_key_id} (User: {user_id}): {str(e)}"
            )
            return {"status": "error", "message": f"Connection test failed: {str(e)}"}
