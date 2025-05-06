# backend/api/routers/settings.py
# -*- coding: utf-8 -*-
"""
API router for user-specific application settings and API key management (Version 1).
"""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any, Optional, Annotated  # Import Annotated

# Import dependencies from the centralized dependencies module
from api.dependencies import (
    get_setting_service,
    get_current_active_user,  # Import user dependency
)

# Import schemas from the main models package
from models import (
    ApiKey,
    ApiKeyCreate,
    UserPreferenceUpdate,
    User,
)  # Import User schema

# Import service type hint
from services.setting_service import SettingService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- API Key Endpoints (User-Aware) ---


@router.get(
    "/api_keys",
    response_model=List[ApiKey],
    summary="List user's API keys",
    description="Retrieve all API keys configured by the current user.",
)
async def get_all_api_keys(
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Retrieve a list of all API keys belonging to the current user."""
    try:
        api_keys = await setting_service.get_all_api_keys(user_id=current_user.id)
        return api_keys
    except Exception as e:
        logger.exception("Failed to retrieve user API keys", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving API keys.")


@router.get(
    "/api_keys/{api_key_id}",
    response_model=ApiKey,
    summary="Get API key by ID",
    description="Retrieve a specific API key by its ID, ensuring it belongs to the user.",
)
async def get_api_key_by_id(
    api_key_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Retrieve details for a single API key owned by the current user."""
    api_key = await setting_service.get_api_key_by_id(
        api_id=api_key_id, user_id=current_user.id
    )
    if not api_key:
        raise HTTPException(
            status_code=404,
            detail=f"API key {api_key_id} not found or not owned by user.",
        )
    return api_key


@router.post(
    "/api_keys",
    response_model=ApiKey,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description="Create a new API key for the current user.",
)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Create a new API key for the current user."""
    # Ensure the data is associated with the current user
    api_key_data_with_user = api_key_data.model_copy(
        update={"user_id": current_user.id}
    )
    try:
        saved_key = await setting_service.save_api_key(
            api_key_data=api_key_data_with_user, user_id=current_user.id
        )
        # Service method now returns the created object or raises error
        return saved_key
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(
            f"Failed to save API key '{api_key_data.model}'", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error saving API key.")


@router.put(
    "/api_keys/{api_key_id}",
    response_model=ApiKey,
    summary="Update an API key",
    description="Update an existing API key belonging to the current user.",
)
async def update_api_key(
    api_key_id: int,
    api_key_data: ApiKeyCreate,  # Use Create schema for update payload
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Update an existing API key owned by the current user."""
    # Ensure the data is associated with the current user for validation
    api_key_data_with_user = api_key_data.model_copy(
        update={"user_id": current_user.id}
    )
    try:
        updated_key = await setting_service.update_api_key(
            api_id=api_key_id,
            user_id=current_user.id,
            api_key_data=api_key_data_with_user,  # Pass the validated data
        )
        if not updated_key:
            # Service returns None if not found/owned
            raise HTTPException(
                status_code=404,
                detail=f"API key {api_key_id} not found or not owned by user.",
            )
        return updated_key
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Failed to update API key ID '{api_key_id}'", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating API key.")


@router.delete(
    "/api_keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key",
    description="Delete an API key belonging to the current user.",
)
async def delete_api_key(
    api_key_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Remove an API key configuration owned by the current user."""
    success = await setting_service.delete_api_key(
        api_id=api_key_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"API key {api_key_id} not found or not owned by user.",
        )
    return None


@router.post(
    "/api_keys/{api_key_id}/test",
    response_model=Dict[str, Any],
    summary="Test API key connection",
    description="Test the connection using a specific API key belonging to the user.",
)
async def test_api_key(
    api_key_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Test connection using an API key owned by the current user."""
    try:
        # Service method now checks ownership
        result = await setting_service.test_api_key_connection(
            api_key_id=api_key_id, user_id=current_user.id
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error testing API key ID {api_key_id}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test API key: {str(e)}")


# --- System Settings Endpoints (User-Aware) ---


@router.get(
    "/settings",
    response_model=Dict[str, Any],
    summary="Get user's application settings",
    description="Retrieve persistent application settings for the current user.",
)
async def get_all_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Fetch settings for the current user, falling back to defaults."""
    try:
        settings = await setting_service.get_all_settings(user_id=current_user.id)
        return settings
    except Exception as e:
        logger.exception("Failed to retrieve user settings", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving settings.")


@router.put(
    "/settings",
    response_model=Dict[str, Any],
    summary="Update user's application settings",
    description="Update persistent application settings for the current user.",
)
async def update_settings(
    settings_update: UserPreferenceUpdate,  # Contains the dict of settings
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Update persistent settings for the current user."""
    try:
        settings_dict = settings_update.settings  # Access the inner dict
        if not settings_dict:
            return await setting_service.get_all_settings(user_id=current_user.id)

        updated_settings = await setting_service.update_settings(
            settings=settings_dict, user_id=current_user.id
        )
        return updated_settings
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        logger.error(f"Settings update failed: {str(re)}")
        raise HTTPException(status_code=500, detail=str(re))
    except Exception as e:
        logger.exception("Failed to update user settings", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating settings.")


@router.post(
    "/settings/reset",
    response_model=Dict[str, Any],
    summary="Reset user's settings to defaults",
    description="Reset persistent settings for the current user to defaults.",
)
async def reset_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    setting_service: Annotated[SettingService, Depends(get_setting_service)],
):
    """Reset persistent settings for the current user to defaults."""
    try:
        reset_settings_values = await setting_service.reset_settings_to_defaults(
            user_id=current_user.id
        )
        return reset_settings_values
    except RuntimeError as re:
        logger.error(f"Settings reset failed: {str(re)}")
        raise HTTPException(status_code=500, detail=str(re))
    except Exception as e:
        logger.exception("Failed to reset user settings", exc_info=True)
        raise HTTPException(status_code=500, detail="Error resetting settings.")
