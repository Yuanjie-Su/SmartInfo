# backend/models/settings.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for user preference settings.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional

# --- User Preference Models ---


class UserPreferenceBase(BaseModel):
    """Base schema for a single user preference setting."""

    config_key: str = Field(..., description="Unique key for the preference setting")
    config_value: str = Field(
        ..., description="Value of the preference setting (stored as string)"
    )
    description: Optional[str] = Field(
        None, description="Optional description of the setting"
    )
    user_id: int = Field(..., description="ID of the user this setting belongs to")


class UserPreference(UserPreferenceBase):
    """Schema representing a user preference setting retrieved from the database."""

    # Inherits all fields from UserPreferenceBase
    # No additional fields like ID needed as config_key is the primary key.

    model_config = ConfigDict(from_attributes=True)


class UserPreferenceUpdate(BaseModel):
    """Schema for updating multiple user preference settings."""

    settings: Dict[str, Any] = Field(
        ..., description="Dictionary of settings to update (key: value pairs)"
    )
