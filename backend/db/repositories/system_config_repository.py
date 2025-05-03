#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
System Config Repository Module
Provides data access operations for system configuration settings
"""

import logging
from typing import List, Optional, Tuple, Dict, Any

from db.schema_constants import (
    SYSTEM_CONFIG_TABLE,
    SYSTEM_CONFIG_KEY,
    SYSTEM_CONFIG_VALUE,
    SYSTEM_CONFIG_DESCRIPTION,
)
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SystemConfigRepository(BaseRepository):
    """Repository for system configuration settings."""

    async def set(
        self, config_key: str, config_value: str, description: str = None
    ) -> bool:
        """
        Sets a configuration value. Creates or updates as needed.

        Args:
            config_key: The unique key for the configuration item
            config_value: The value to store
            description: Optional description of the configuration item

        Returns:
            True if successful, False otherwise
        """
        # Check if key exists
        existing = await self.get(config_key)

        if existing:
            # Update existing record
            query_str = f"""
                UPDATE {SYSTEM_CONFIG_TABLE} 
                SET {SYSTEM_CONFIG_VALUE} = ?, {SYSTEM_CONFIG_DESCRIPTION} = ?
                WHERE {SYSTEM_CONFIG_KEY} = ?
            """
            try:
                cursor = await self._execute(
                    query_str, (config_value, description, config_key), commit=True
                )
                updated = self._get_rows_affected(cursor) > 0
                if updated:
                    logger.info(
                        f"Updated config key {config_key} to value '{config_value}'."
                    )
                return updated
            except Exception as e:
                logger.error(f"Error updating system config: {e}")
                return False
        else:
            # Insert new record
            query_str = f"""
                INSERT INTO {SYSTEM_CONFIG_TABLE} ({SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION})
                VALUES (?, ?, ?)
            """
            try:
                cursor = await self._execute(
                    query_str, (config_key, config_value, description), commit=True
                )
                inserted = self._get_rows_affected(cursor) > 0
                if inserted:
                    logger.info(
                        f"Added new config key {config_key} with value '{config_value}'."
                    )
                return inserted
            except Exception as e:
                logger.error(f"Error adding system config: {e}")
                return False

    async def get(self, config_key: str) -> Optional[Tuple[str, str, str]]:
        """
        Gets a configuration item by key.

        Args:
            config_key: The key to look up

        Returns:
            Tuple of (config_key, config_value, description) or None if not found
        """
        query_str = f"""
            SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION}
            FROM {SYSTEM_CONFIG_TABLE} WHERE {SYSTEM_CONFIG_KEY} = ?
        """
        try:
            return await self._fetchone(query_str, (config_key,))
        except Exception as e:
            logger.error(f"Error getting system config by key: {e}")
            return None

    async def get_all(self) -> Dict[str, str]:
        """
        Gets all configuration items as a key-value dictionary.

        Returns:
            Dictionary mapping config_keys to config_values
        """
        query_str = f"SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE} FROM {SYSTEM_CONFIG_TABLE}"
        try:
            rows = await self._fetchall(query_str)
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting all system configs: {e}")
            return {}

    async def get_all_with_details(self) -> List[Dict[str, str]]:
        """
        Gets all configuration items with full details.

        Returns:
            List of dictionaries with config_key, config_value, and description
        """
        query_str = f"""
            SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION}
            FROM {SYSTEM_CONFIG_TABLE} ORDER BY {SYSTEM_CONFIG_KEY}
        """
        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting all system configs with details: {e}")
            return []

    async def delete(self, config_key: str) -> bool:
        """
        Deletes a configuration item by key.

        Args:
            config_key: The key to delete

        Returns:
            True if deleted, False otherwise
        """
        query_str = f"DELETE FROM {SYSTEM_CONFIG_TABLE} WHERE {SYSTEM_CONFIG_KEY} = ?"
        try:
            cursor = await self._execute(query_str, (config_key,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0
            if deleted:
                logger.info(f"Deleted config key {config_key}.")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting system config: {e}")
            return False

    async def clear_all(self) -> bool:
        """
        Deletes all configuration items.

        Returns:
            True if successful, False otherwise
        """
        query_str = f"DELETE FROM {SYSTEM_CONFIG_TABLE}"
        try:
            cursor = await self._execute(query_str, commit=True)
            rows_affected = self._get_rows_affected(cursor)
            logger.warning(
                f"Cleared all system configuration settings ({rows_affected} items)."
            )
            return True
        except Exception as e:
            logger.error(f"Error clearing all system configs: {e}")
            return False
