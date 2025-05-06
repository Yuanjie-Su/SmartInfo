#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setting service for managing user-specific application settings and API keys
"""

import logging
import json
from typing import Dict, Any, List, Optional, Union

# Import using backend package path
from db.repositories.api_key_repository import ApiKeyRepository
from db.repositories.user_preference_repository import UserPreferenceRepository
from models import (
    ApiKey,
    ApiKeyCreate,
    UserPreference,
    UserPreferenceBase,
    User,
)  # Import relevant models

from core.llm.client import AsyncLLMClient

logger = logging.getLogger(__name__)


class SettingService:
    """Service for managing user-specific application settings and API keys"""

    def __init__(
        self,
        api_key_repo: ApiKeyRepository,
        user_preference_repo: UserPreferenceRepository,
    ):
        """Initialize the setting service"""
        self._api_key_repo = api_key_repo
        self._user_preference_repo = user_preference_repo

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

    # --- User Preference Management (User-Aware) ---

    async def get_all_settings(self, user_id: int) -> Dict[str, Any]:
        """Get all application settings for a specific user."""
        user_settings = await self._user_preference_repo.get_all(user_id)
        # Return the dictionary fetched directly from the repo
        return user_settings

    async def update_settings(
        self, settings: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """Update application settings for a specific user."""
        if not settings:
            return await self.get_all_settings(user_id)

        # Note: With config simplified, we no longer have a list of valid persistent keys here.
        # This means any key can be saved. If we need validation, we'd need a separate source
        # of truth for valid user preference keys. For now, save whatever is provided.

        # Save each setting to the database for the user
        all_success = True
        for key, value in settings.items():
            # Convert value to string for storage (repo expects string)
            str_value = str(value)
            success = await self._user_preference_repo.set(
                config_key=key,
                config_value=str_value,
                user_id=user_id,
                description=None,  # No default descriptions available from config anymore
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
        success = await self._user_preference_repo.clear_all_for_user(user_id)

        if not success:
            logger.error(
                f"Failed to clear existing user preferences from DB for user {user_id} during reset."
            )
            # Depending on requirements, might want to raise an error here
            # raise RuntimeError(f"Failed to clear existing user preferences for user {user_id}")

        # Return an empty dictionary as there are no defaults managed by this service anymore
        return {}

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
                model=model,
                max_output_tokens=max_output_tokens,
            ) as client:
                response = await client.chat_completion(messages=test_messages)
                response["status"] = "success"
                return response
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": f"Failed to connect to {base_url} with model {model}",
            }
