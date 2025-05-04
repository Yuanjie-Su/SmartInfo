#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
System Config Repository Module
Provides data access operations for system configuration settings
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

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
        self, config_key: str, config_value: str, description: Optional[str] = None
    ) -> bool:
        """
        Sets a configuration value. Creates or updates as needed using ON CONFLICT.

        Args:
            config_key: The unique key for the configuration item
            config_value: The value to store
            description: Optional description of the configuration item

        Returns:
            True if successful, False otherwise
        """
        # Change placeholders to $n, use INSERT ... ON CONFLICT DO UPDATE for upsert
        query_str = f"""
            INSERT INTO {SYSTEM_CONFIG_TABLE} ({SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION})
            VALUES ($1, $2, $3)
            ON CONFLICT ({SYSTEM_CONFIG_KEY}) DO UPDATE SET
                {SYSTEM_CONFIG_VALUE} = EXCLUDED.{SYSTEM_CONFIG_VALUE},
                {SYSTEM_CONFIG_DESCRIPTION} = EXCLUDED.{SYSTEM_CONFIG_DESCRIPTION}
        """
        params = (config_key, config_value, description)

        try:
            # Use _execute, success is determined by no exception
            status = await self._execute(query_str, params)
            # Status will be "INSERT 0 1" or "UPDATE 1" or potentially "INSERT 0 0" if row exists and values are identical
            success = status is not None and (
                status.startswith("INSERT") or status.startswith("UPDATE")
            )
            if success:
                logger.info(
                    f"Set config key '{config_key}'. Status: {status}"  # Value not logged for potential sensitivity
                )
            else:
                # This might happen if the command didn't change anything or failed silently (less likely)
                logger.warning(
                    f"Set command for config key '{config_key}' executed but status was '{status}'."
                )
            # Return True if execute didn't raise an error, as ON CONFLICT handles upsert logic
            return True

        except asyncpg.PostgresError as e:
            logger.error(f"Error setting system config key '{config_key}': {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error setting system config key '{config_key}': {e}"
            )
            return False

    async def get(self, config_key: str) -> Optional[asyncpg.Record]:
        """
        Gets a configuration item by key.

        Args:
            config_key: The key to look up

        Returns:
            asyncpg.Record of (config_key, config_value, description) or None if not found
        """
        # Change placeholder to $1
        query_str = f"""
            SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION}
            FROM {SYSTEM_CONFIG_TABLE} WHERE {SYSTEM_CONFIG_KEY} = $1
        """
        try:
            # Use _fetchone directly
            return await self._fetchone(query_str, (config_key,))
        except Exception as e:
            logger.error(f"Error getting system config by key '{config_key}': {e}")
            return None

    async def get_all(self) -> Dict[str, str]:
        """
        Gets all configuration items as a key-value dictionary.

        Returns:
            Dictionary mapping config_keys to config_values
        """
        query_str = f"SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE} FROM {SYSTEM_CONFIG_TABLE}"
        try:
            # Use _fetchall directly
            records = await self._fetchall(query_str)
            # Convert list of Records to dict
            return {
                record[SYSTEM_CONFIG_KEY.lower()]: record[SYSTEM_CONFIG_VALUE.lower()]
                for record in records
            }
        except Exception as e:
            logger.error(f"Error getting all system configs: {e}")
            return {}

    async def get_all_with_details(self) -> List[asyncpg.Record]:
        """
        Gets all configuration items with full details.

        Returns:
            List of asyncpg.Record objects with config_key, config_value, and description
        """
        query_str = f"""
            SELECT {SYSTEM_CONFIG_KEY}, {SYSTEM_CONFIG_VALUE}, {SYSTEM_CONFIG_DESCRIPTION}
            FROM {SYSTEM_CONFIG_TABLE} ORDER BY {SYSTEM_CONFIG_KEY}
        """
        try:
            # Use _fetchall directly (which calls base _fetchall)
            return await self._fetchall(query_str)
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
        # Change placeholder to $1
        query_str = f"DELETE FROM {SYSTEM_CONFIG_TABLE} WHERE {SYSTEM_CONFIG_KEY} = $1"
        try:
            # Use _execute and check status
            status = await self._execute(query_str, (config_key,))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted config key {config_key}.")
            else:
                logger.warning(
                    f"Delete command for config key {config_key} executed but status was '{status}'."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting system config '{config_key}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting system config '{config_key}': {e}")
            return False

    async def clear_all(self) -> bool:
        """
        Deletes all configuration items.

        Returns:
            True if successful, False otherwise
        """
        query_str = f"DELETE FROM {SYSTEM_CONFIG_TABLE}"
        try:
            # Use _execute, success is no exception
            status = await self._execute(query_str)
            logger.warning(
                f"Cleared all system configuration settings. Status: {status}."
            )
            return True
        except asyncpg.PostgresError as e:
            logger.error(f"Error clearing all system configs: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error clearing all system configs: {e}")
            return False
