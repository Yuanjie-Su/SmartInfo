# backend/models/settings.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for system configuration settings.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional

# --- System Configuration Models ---


class SystemConfigBase(BaseModel):
    """Base schema for a single system configuration setting."""

    config_key: str = Field(..., description="Unique key for the configuration setting")
    config_value: str = Field(
        ..., description="Value of the configuration setting (stored as string)"
    )
    description: Optional[str] = Field(
        None, description="Optional description of the setting"
    )


class SystemConfig(SystemConfigBase):
    """Schema representing a system configuration setting retrieved from the database."""

    # Inherits all fields from SystemConfigBase
    # No additional fields like ID needed as config_key is the primary key.

    model_config = ConfigDict(from_attributes=True)


class SystemConfigUpdate(BaseModel):
    """Schema for updating multiple system settings."""

    settings: Dict[str, Any] = Field(
        ..., description="Dictionary of settings to update (key: value pairs)"
    )
