#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
User Preference Repository Module
Provides data access operations for user preference settings
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

from db.schema_constants import (
    USER_PREFERENCES_TABLE,
    USER_PREFERENCE_KEY,
    USER_PREFERENCE_VALUE,
    USER_PREFERENCE_DESCRIPTION,
    USER_PREFERENCE_USER_ID,  # Import user_id constant
)
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserPreferenceRepository(BaseRepository):
    """Repository for user-specific preference settings."""

    async def set(
        self,
        config_key: str,
        config_value: str,
        user_id: int,
        description: Optional[str] = None,
    ) -> bool:
        """
        Sets a preference value for a specific user. Creates or updates as needed.

        Args:
            config_key: The unique key for the preference item.
            config_value: The value to store.
            user_id: The ID of the user this setting belongs to.
            description: Optional description of the preference item.

        Returns:
            True if successful, False otherwise.
        """
        query_str = f"""
            INSERT INTO {USER_PREFERENCES_TABLE} ({USER_PREFERENCE_KEY}, {USER_PREFERENCE_VALUE}, {USER_PREFERENCE_DESCRIPTION}, {USER_PREFERENCE_USER_ID})
            VALUES ($1, $2, $3, $4)
            ON CONFLICT ({USER_PREFERENCE_KEY}, {USER_PREFERENCE_USER_ID}) DO UPDATE SET
                {USER_PREFERENCE_VALUE} = EXCLUDED.{USER_PREFERENCE_VALUE},
                {USER_PREFERENCE_DESCRIPTION} = EXCLUDED.{USER_PREFERENCE_DESCRIPTION}
        """
        params = (config_key, config_value, description, user_id)

        try:
            status = await self._execute(query_str, params)
            success = status is not None and (
                status.startswith("INSERT") or status.startswith("UPDATE")
            )
            if success:
                logger.info(
                    f"Set preference key '{config_key}' for user {user_id}. Status: {status}"
                )
            else:
                logger.warning(
                    f"Set command for preference key '{config_key}' (User: {user_id}) executed but status was '{status}'."
                )
            return True

        except asyncpg.PostgresError as e:
            logger.error(
                f"Error setting user preference key '{config_key}' for user {user_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error setting user preference key '{config_key}' for user {user_id}: {e}"
            )
            return False

    async def get(self, config_key: str, user_id: int) -> Optional[asyncpg.Record]:
        """
        Gets a preference item by key for a specific user.

        Args:
            config_key: The key to look up.
            user_id: The ID of the user.

        Returns:
            asyncpg.Record of (config_key, config_value, description, user_id) or None if not found.
        """
        query_str = f"""
            SELECT {USER_PREFERENCE_KEY}, {USER_PREFERENCE_VALUE}, {USER_PREFERENCE_DESCRIPTION}, {USER_PREFERENCE_USER_ID}
            FROM {USER_PREFERENCES_TABLE} WHERE {USER_PREFERENCE_KEY} = $1 AND {USER_PREFERENCE_USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (config_key, user_id))
        except Exception as e:
            logger.error(
                f"Error getting user preference by key '{config_key}' for user {user_id}: {e}"
            )
            return None

    async def get_all(self, user_id: int) -> Dict[str, str]:
        """
        Gets all preference items for a specific user as a key-value dictionary.

        Args:
            user_id: The ID of the user.

        Returns:
            Dictionary mapping config_keys to config_values for the user.
        """
        query_str = f"SELECT {USER_PREFERENCE_KEY}, {USER_PREFERENCE_VALUE} FROM {USER_PREFERENCES_TABLE} WHERE {USER_PREFERENCE_USER_ID} = $1"
        try:
            records = await self._fetchall(query_str, (user_id,))
            return {
                record[USER_PREFERENCE_KEY.lower()]: record[
                    USER_PREFERENCE_VALUE.lower()
                ]
                for record in records
            }
        except Exception as e:
            logger.error(f"Error getting all user preferences for user {user_id}: {e}")
            return {}

    async def get_all_with_details(self, user_id: int) -> List[asyncpg.Record]:
        """
        Gets all preference items with full details for a specific user.

        Args:
            user_id: The ID of the user.

        Returns:
            List of asyncpg.Record objects with config_key, config_value, description, user_id.
        """
        query_str = f"""
            SELECT {USER_PREFERENCE_KEY}, {USER_PREFERENCE_VALUE}, {USER_PREFERENCE_DESCRIPTION}, {USER_PREFERENCE_USER_ID}
            FROM {USER_PREFERENCES_TABLE}
            WHERE {USER_PREFERENCE_USER_ID} = $1
            ORDER BY {USER_PREFERENCE_KEY}
        """
        try:
            return await self._fetchall(query_str, (user_id,))
        except Exception as e:
            logger.error(
                f"Error getting all user preferences with details for user {user_id}: {e}"
            )
            return []

    async def delete(self, config_key: str, user_id: int) -> bool:
        """
        Deletes a preference item by key for a specific user.

        Args:
            config_key: The key to delete.
            user_id: The ID of the user.

        Returns:
            True if deleted, False otherwise.
        """
        query_str = f"DELETE FROM {USER_PREFERENCES_TABLE} WHERE {USER_PREFERENCE_KEY} = $1 AND {USER_PREFERENCE_USER_ID} = $2"
        try:
            status = await self._execute(query_str, (config_key, user_id))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(
                    f"Deleted preference key '{config_key}' for user {user_id}."
                )
            else:
                logger.warning(
                    f"Delete command for preference key '{config_key}' (User: {user_id}) executed but status was '{status}'. Key might not exist or belong to user."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error deleting user preference '{config_key}' for user {user_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting user preference '{config_key}' for user {user_id}: {e}"
            )
            return False

    async def clear_all_for_user(self, user_id: int) -> bool:
        """
        Deletes all preference items for a specific user.

        Args:
            user_id: The ID of the user whose settings to clear.

        Returns:
            True if successful, False otherwise.
        """
        query_str = (
            f"DELETE FROM {USER_PREFERENCES_TABLE} WHERE {USER_PREFERENCE_USER_ID} = $1"
        )
        try:
            status = await self._execute(query_str, (user_id,))
            logger.warning(
                f"Cleared user preference settings for user {user_id}. Status: {status}."
            )
            return True
        except asyncpg.PostgresError as e:
            logger.error(f"Error clearing user preferences for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error clearing user preferences for user {user_id}: {e}"
            )
            return False
