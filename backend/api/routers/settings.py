# backend/api/routers/settings.py
# -*- coding: utf-8 -*-
"""
API router for application settings and API key management (Version 1).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any, Optional

# Import dependencies from the centralized dependencies module
from backend.api.dependencies import (
    get_setting_service,
    get_llm_pool_dependency,
)

# Import schemas from the main models package
from backend.models.schemas.api_key import ApiKey, ApiKeyCreate
from backend.models.schemas.settings import SystemConfigUpdate

# Import service and pool type hints
from backend.services.setting_service import SettingService
from backend.core.llm.pool import LLMClientPool  # Corrected import path

logger = logging.getLogger(__name__)

router = APIRouter()

# --- API Key Endpoints ---


@router.get(
    "/api_keys",
    response_model=List[ApiKey],
    summary="List all API keys",
    description="Retrieve all configured API keys stored in the database.",
)
async def get_all_api_keys(
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Retrieve a list of all API keys. The actual key values are included.
    Handle with care in frontend applications.
    """
    try:
        api_keys = await setting_service.get_all_api_keys()
        # The service returns ApiKey objects which FastAPI serializes
        return api_keys
    except Exception as e:
        logger.exception("Failed to retrieve all API keys", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving API keys.",
        )


@router.get(
    "/api_keys/{api_name}",
    response_model=ApiKey,
    summary="Get API key by name",
    description="Retrieve a specific API key by its configured name.",
)
async def get_api_key_by_name(
    api_name: str, setting_service: SettingService = Depends(get_setting_service)
):
    """
    Retrieve details for a single API key identified by its name.
    """
    api_key = await setting_service.get_api_key_by_name(api_name)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key with name '{api_name}' not found.",
        )
    return api_key


@router.post(
    "/api_keys",
    response_model=ApiKey,
    status_code=status.HTTP_201_CREATED,
    summary="Save or update an API key",
    description="Create a new API key or update an existing one if the name matches.",
)
async def save_api_key(
    api_key_data: ApiKeyCreate,
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Save an API key. If an entry with the same `api_name` exists, it updates
    the `api_key` and `description`. Otherwise, it creates a new entry.
    """
    try:
        # The service's save_api_key handles both create and update logic
        saved_key = await setting_service.save_api_key(
            api_name=api_key_data.api_name,
            api_key=api_key_data.api_key,
            description=api_key_data.description,
        )
        if not saved_key:  # Should not happen if service throws exceptions correctly
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save API key.",
            )
        return saved_key
    except ValueError as ve:
        # Catches validation errors like missing name/key from the service
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception(
            f"Failed to save API key '{api_key_data.api_name}'", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the API key.",
        )


@router.put(
    "/api_keys/{api_name}",
    response_model=ApiKey,
    summary="Explicitly update an API key",
    description="Update the key value or description for an existing API key identified by name.",
)
async def update_api_key(
    api_name: str,
    # Re-using ApiKeyCreate schema for update payload as it contains all necessary fields
    api_key_data: ApiKeyCreate,
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Update an existing API key. This endpoint requires the API key name in the path
    and expects the new key value and optional description in the body.
    Returns 404 if the API key name does not exist.
    """
    try:
        # The service's update_api_key specifically handles updates for existing keys
        updated_key = await setting_service.update_api_key(
            api_name=api_name,
            api_key=api_key_data.api_key,
            description=api_key_data.description,
        )
        if not updated_key:
            # Service returns None if the key wasn't found for update
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with name '{api_name}' not found.",
            )
        return updated_key
    except ValueError as ve:
        # Catches validation errors like missing name/key
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception(f"Failed to update API key '{api_name}'", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the API key.",
        )


@router.delete(
    "/api_keys/{api_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key",
    description="Delete an API key from the database by its name.",
)
async def delete_api_key(
    api_name: str, setting_service: SettingService = Depends(get_setting_service)
):
    """
    Remove an API key configuration using its unique name.
    """
    success = await setting_service.delete_api_key(api_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key with name '{api_name}' not found or deletion failed.",
        )
    return None  # No content on success


# --- System Settings Endpoints ---


@router.get(
    "/settings",
    response_model=Dict[str, Any],
    summary="Get application settings",
    description="Retrieve all persistent application settings.",
)
async def get_all_settings(
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Fetch the current values of all settings managed by the application configuration,
    primarily those stored persistently in the database.
    """
    try:
        settings = await setting_service.get_all_settings()
        return settings
    except Exception as e:
        logger.exception("Failed to retrieve application settings", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving settings.",
        )


@router.put(
    "/settings",
    response_model=Dict[str, Any],
    summary="Update application settings",
    description="Update one or more persistent application settings.",
)
async def update_settings(
    # Body receives a dict of settings to update
    settings_update: SystemConfigUpdate,
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Update persistent application settings with the provided values.
    Only valid settings keys will be accepted.
    """
    try:
        # The settings_update is a Pydantic model - convert to dict for service
        settings_dict = settings_update.model_dump()
        # Only include non-None values in the update
        settings_to_update = {k: v for k, v in settings_dict.items() if v is not None}

        if not settings_to_update:
            # If nothing to update, just return current settings
            return await setting_service.get_all_settings()

        # Update settings via service
        updated_settings = await setting_service.update_settings(settings_to_update)
        return updated_settings

    except ValueError as ve:
        # For validation errors (invalid keys, etc.)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except RuntimeError as re:
        # For persistence/save failures
        logger.error(f"Settings update failed: {str(re)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(re),
        )
    except Exception as e:
        # Unexpected errors
        logger.exception("Failed to update application settings", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating settings.",
        )


@router.post(
    "/settings/reset",
    response_model=Dict[str, Any],
    summary="Reset settings to defaults",
    description="Reset all persistent application settings to their default values.",
)
async def reset_settings(
    setting_service: SettingService = Depends(get_setting_service),
):
    """
    Reset all persistent application settings to their factory default values.
    This action cannot be undone.
    """
    try:
        # The service handles the reset logic
        reset_settings = await setting_service.reset_settings_to_defaults()
        return reset_settings

    except RuntimeError as re:
        # For persistence/save failures
        logger.error(f"Settings reset failed: {str(re)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(re),
        )
    except Exception as e:
        # Unexpected errors
        logger.exception("Failed to reset application settings", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting settings to defaults.",
        )


# --- LLM Service Status Endpoints ---


@router.get(
    "/llm/test",
    summary="Test LLM service connection",
    response_model=Dict[str, Any],
    description="Verify connectivity and basic functionality of the configured LLM service.",
)
async def test_llm_connection(
    # Inject the LLM pool dependency
    llm_pool: LLMClientPool = Depends(get_llm_pool_dependency),
):
    """
    Test the connection to the LLM service by sending a simple request.
    Returns success status and response time, or error details if the request fails.
    """
    try:
        # Get a client to test with
        llm_client = llm_pool.get_client()

        # Simple test prompt
        test_prompt = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello to verify connectivity."},
        ]

        # Track start time for response timing
        import time

        start_time = time.time()

        # Execute test call
        response = await llm_client.agenerate_response(test_prompt)

        # Calculate response time
        response_time = round((time.time() - start_time) * 1000, 2)  # ms

        # Return success payload
        return {
            "status": "success",
            "response": response[:100] + "..." if len(response) > 100 else response,
            "response_time_ms": response_time,
            "model": llm_client.model_name,
        }

    except Exception as e:
        # Return error information
        logger.error(f"LLM connection test failed: {str(e)}", exc_info=True)
        error_message = str(e)
        error_type = type(e).__name__

        return {
            "status": "error",
            "error_type": error_type,
            "error_message": error_message,
            "suggestion": "Check your API key configuration and network connectivity.",
        }
