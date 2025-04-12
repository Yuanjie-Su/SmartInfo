#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
System Configuration Repository Module
"""

import logging
from typing import Dict, Optional

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class SystemConfigRepository(BaseRepository):
    """Repository for system_config table operations."""

    def get_config(self, key: str) -> Optional[str]:
        """Gets a system config value by key."""
        query = "SELECT config_value FROM system_config WHERE config_key = ?"
        result = self._fetchone(query, (key,))
        return result[0] if result else None

    def save_config(
        self, key: str, value: str, description: Optional[str] = None
    ) -> bool:
        """Saves or updates a system config value."""
        query = """
             INSERT INTO system_config (config_key, config_value, description)
             VALUES (?, ?, ?)
             ON CONFLICT(config_key) DO UPDATE SET
                 config_value = excluded.config_value,
                 description = COALESCE(excluded.description, description)
         """
        cursor = self._execute(query, (key, value, description), commit=True)
        saved = cursor is not None
        if saved:
            logger.info(f"Saved/Updated system config key '{key}'.")
        return saved

    def get_all_configs(self) -> Dict[str, str]:
        """Gets all system configurations."""
        query = "SELECT config_key, config_value FROM system_config"
        rows = self._fetchall(query)
        return {row[0]: row[1] for row in rows}

    def delete_config(self, key: str) -> bool:
        """Deletes a system config key."""
        query = "DELETE FROM system_config WHERE config_key = ?"
        cursor = self._execute(query, (key,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted system config key '{key}'.")
        return deleted

    def delete_all(self) -> bool:
        """Deletes all system config keys."""
        logger.warning("Attempting to clear all system configuration.")
        cursor = self._execute("DELETE FROM system_config", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from system_config table.")
        return cleared 