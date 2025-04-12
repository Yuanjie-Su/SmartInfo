# backend/api/routers/settings_router.py
"""
REST API endpoints for settings-related operations.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query

# Local project imports
from backend.services.setting_service import SettingService
from backend.api.dependencies import get_setting_service
from backend.api.schemas.settings import (
    ApiKeyInfo, # Use this for listing keys (no value)
    ApiKeyCreate, # Use for POST and PUT body
    SystemConfig, # Use for listing configs and GET by key
    SystemConfigUpdate, # Use for PUT body
    ApiConnectionTestResult # Use for test connection endpoint
)

router = APIRouter()
logger = logging.getLogger(__name__)

# --- API Keys ---
@router.get("/api-keys", response_model=List[ApiKeyInfo])
async def list_api_keys(
    setting_service: SettingService = Depends(get_setting_service)
):
    """Get info (name, dates) for all API keys stored in the database."""
    try:
        # Service returns List[Dict] matching ApiKeyInfo
        return await setting_service.list_api_keys_info()
    except Exception as e:
        logger.error(f"Error listing API keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error listing API keys.")

@router.get("/api-keys/{api_name}", response_model=Dict[str, Optional[str]])
async def get_api_key_value(
    api_name: str,
    setting_service: SettingService = Depends(get_setting_service)
):
    """
    Get the value of a specific API key.
    Returns {"api_key": "value"} or {"api_key": null} if not found/set.
    Note: Be cautious about exposing keys via API. Environment variables are preferred.
    """
    try:
        key_value = setting_service.get_api_key(api_name) # Service handles env priority
        # Return even if None, to indicate if it's set or not
        return {"api_key": key_value}
    except Exception as e:
        logger.error(f"Error getting API key value for '{api_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error getting API key value.")


@router.post("/api-keys", response_model=ApiKeyInfo, status_code=201)
async def save_api_key(
    key_data: ApiKeyCreate,
    setting_service: SettingService = Depends(get_setting_service)
):
    """
    Save or update an API key in the database.
    Returns info about the saved key.
    Note: Environment variables will still override this during runtime usage.
    """
    try:
        success = await setting_service.save_api_key(key_data.api_name, key_data.api_key)
        if not success:
             # Could be DB error
             raise HTTPException(status_code=500, detail="Failed to save API key to database.")

        # Fetch the info of the key that was just saved/updated
        keys_info = await setting_service.list_api_keys_info()
        for key_info in keys_info:
            if key_info['api_name'] == key_data.api_name:
                 return ApiKeyInfo.model_validate(key_info)

        # Should not happen if save was successful
        raise HTTPException(status_code=500, detail="Failed to retrieve saved API key info.")

    except Exception as e:
        logger.error(f"Error saving API key '{key_data.api_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error saving API key.")

# No PUT needed if POST handles insert/update via ON CONFLICT

@router.delete("/api-keys/{api_name}", status_code=204)
async def delete_api_key(
    api_name: str,
    setting_service: SettingService = Depends(get_setting_service)
):
    """Delete an API key from the database."""
    try:
        success = await setting_service.delete_api_key_from_db(api_name)
        if not success:
            # It might not have existed in the DB, but that's still successful deletion conceptually
            logger.warning(f"Attempted to delete API key '{api_name}' from DB, but it was not found.")
            # Return 204 even if not found, as the desired state (not present) is achieved
            # Alternatively, could return 404 if strict "must exist to delete" is needed
            pass # Fall through to return 204
        return None
    except Exception as e:
         logger.error(f"Error deleting API key '{api_name}' from DB: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Internal server error deleting API key.")


# --- System Config ---
@router.get("/config", response_model=Dict[str, Any])
async def get_all_system_settings(
    setting_service: SettingService = Depends(get_setting_service)
):
    """Get all current persistent system settings."""
    try:
        # Service returns the dictionary directly
        return await setting_service.get_all_settings()
    except Exception as e:
        logger.error(f"Error getting all system settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error getting system settings.")


@router.get("/config/{key}", response_model=SystemConfig)
async def get_system_setting(
    key: str,
    setting_service: SettingService = Depends(get_setting_service)
):
    """Get a specific system configuration value by key."""
    try:
        # Check if key is valid based on defaults? Service/Config might handle this.
        value = await setting_service.get_setting(key)
        if value is None:
            # Distinguish between key not existing vs. value being null?
            # Check if key is known in defaults
             if key not in setting_service._config.DEFAULT_PERSISTENT_CONFIG:
                 raise HTTPException(status_code=404, detail=f"System config key '{key}' not found or not defined.")
            # If key is known but value is None (perhaps default is None), return it
        return SystemConfig(config_key=key, config_value=value)
    except Exception as e:
        logger.error(f"Error getting system setting '{key}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error getting system setting '{key}'.")


@router.put("/config/{key}", response_model=SystemConfig)
async def update_system_setting(
    key: str,
    config_update: SystemConfigUpdate,
    setting_service: SettingService = Depends(get_setting_service)
):
    """Update a system configuration value."""
    try:
        # The service's save_setting handles setting in memory and saving all to DB
        success = await setting_service.save_setting(key, config_update.config_value)
        if not success:
             # Failure could be DB error or invalid key (if service enforced it)
             raise HTTPException(status_code=400, detail=f"Failed to save system setting '{key}'. Invalid key or DB error.")

        # Return the updated value
        updated_value = await setting_service.get_setting(key)
        return SystemConfig(config_key=key, config_value=updated_value)
    except Exception as e:
        logger.error(f"Error updating system setting '{key}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error updating system setting '{key}'.")


# POST for creating is less common if PUT handles upsert, but can be added if needed.
# Use SystemConfigCreate schema if added.


@router.delete("/config/{key}", status_code=204)
async def delete_system_setting(
    key: str,
    setting_service: SettingService = Depends(get_setting_service)
):
    """Delete a system configuration setting (resets to default in memory, removes from DB)."""
    try:
        success = await setting_service.delete_setting(key)
        if not success:
             # May fail if DB operation fails
             raise HTTPException(status_code=500, detail=f"Failed to delete system setting '{key}' from database.")
        # If the key wasn't in the DB but memory was reset, it's still considered success
        return None
    except Exception as e:
        logger.error(f"Error deleting system setting '{key}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error deleting system setting '{key}'.")


@router.post("/config/reset-defaults", status_code=200)
async def reset_all_settings_to_defaults(
    setting_service: SettingService = Depends(get_setting_service)
):
    """Reset all persistent settings to their default values."""
    try:
        success = await setting_service.reset_settings_to_defaults()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset settings to defaults.")
        return {"message": "System settings reset to defaults successfully."}
    except Exception as e:
        logger.error(f"Error resetting settings to defaults: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error resetting settings.")