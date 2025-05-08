#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API Key Repository Module
Provides data access operations for API keys
"""

import logging
import time
from typing import List, Optional, Tuple, Dict, Any, Union
import asyncpg
from datetime import datetime, timezone


from db.schema_constants import ApiConfig

# Note: Assuming 'user_id' column exists conceptually in API_CONFIG_TABLE
API_CONFIG_USER_ID = "user_id"

from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ApiKeyRepository(BaseRepository):
    """Repository for API key management operations."""

    async def add(
        self,
        model: str,
        base_url: str,
        api_key: str,
        context: int,
        max_output_tokens: int,
        user_id: int,  # Add user_id
        description: str = None,
    ) -> Optional[int]:
        """Adds a new API key configuration for a user. Returns new ID or None if failed."""
        current_time = datetime.now(timezone.utc)
        query_str = f"""
            INSERT INTO {ApiConfig.TABLE_NAME} (
                {ApiConfig.MODEL}, {ApiConfig.BASE_URL}, {ApiConfig.API_KEY},
                {ApiConfig.CONTEXT}, {ApiConfig.MAX_OUTPUT_TOKENS}, {ApiConfig.DESCRIPTION},
                {ApiConfig.CREATED_DATE}, {ApiConfig.MODIFIED_DATE}, {ApiConfig.USER_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING {ApiConfig.ID}
        """
        params = (
            model,
            base_url,
            api_key,
            context,
            max_output_tokens,
            description,
            current_time,
            current_time,
            user_id,  # Add user_id
        )

        try:
            last_id = await self._fetchval(query_str, params)

            if last_id is not None:
                logger.info(
                    f"Added API key for model {model} with ID {last_id} for user {user_id}."
                )
            else:
                logger.warning(
                    f"Failed to add API key for model {model} for user {user_id}, no ID returned."
                )
            return last_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding API key for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding API key for user {user_id}: {e}")
            return None

    async def update(
        self,
        api_id: int,
        user_id: int,  # Add user_id
        model: str,
        base_url: str,
        api_key: str = None,
        context: int = None,
        max_output_tokens: int = None,
        description: str = None,
    ) -> bool:
        """Updates an API key by ID for a specific user."""
        # Check ownership first
        existing_record = await self.get_by_id(api_id, user_id)
        if not existing_record:
            logger.warning(
                f"Failed to update API key ID {api_id} for user {user_id} (not found or not owned)."
            )
            return False
        existing = dict(existing_record)

        current_time = datetime.now(timezone.utc)
        query_str = f"""
            UPDATE {ApiConfig.TABLE_NAME}
            SET {ApiConfig.MODEL} = $1, {ApiConfig.BASE_URL} = $2,
                {ApiConfig.API_KEY} = $3, {ApiConfig.CONTEXT} = $4,
                {ApiConfig.MAX_OUTPUT_TOKENS} = $5, {ApiConfig.DESCRIPTION} = $6,
                {ApiConfig.MODIFIED_DATE} = $7
            WHERE {ApiConfig.ID} = $8 AND {ApiConfig.USER_ID} = $9
        """
        params = (
            model,
            base_url,
            api_key if api_key is not None else existing[API_CONFIG_API_KEY.lower()],
            context if context is not None else existing[API_CONFIG_CONTEXT.lower()],
            (
                max_output_tokens
                if max_output_tokens is not None
                else existing[API_CONFIG_MAX_OUTPUT_TOKENS.lower()]
            ),
            (
                description
                if description is not None
                else existing.get(
                    API_CONFIG_DESCRIPTION.lower()
                )  # Use .get for optional field
            ),
            current_time,
            api_id,
            user_id,  # Add user_id to WHERE clause
        )

        try:
            status = await self._execute(query_str, params)
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated API key ID {api_id} for user {user_id}.")
            else:
                # This case should ideally not happen if get_by_id check passed, but log just in case
                logger.warning(
                    f"Update command for API key ID {api_id} (User: {user_id}) executed but status was '{status}'."
                )
            return updated
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating API key for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating API key for user {user_id}: {e}")
            return False

    async def delete(self, api_id: int, user_id: int) -> bool:
        """Deletes an API key by ID for a specific user."""
        query_str = f"DELETE FROM {ApiConfig.TABLE_NAME} WHERE {ApiConfig.ID} = $1 AND {ApiConfig.USER_ID} = $2"

        try:
            status = await self._execute(query_str, (api_id, user_id))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted API key ID {api_id} for user {user_id}.")
            else:
                logger.warning(
                    f"Delete command for API key ID {api_id} (User: {user_id}) executed but status was '{status}'. Key might not exist or belong to user."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting API key for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting API key for user {user_id}: {e}")
            return False

    async def get_by_id(self, api_id: int, user_id: int) -> Optional[asyncpg.Record]:
        """Gets an API key by ID for a specific user."""
        query_str = f"""
            SELECT {ApiConfig.ID}, {ApiConfig.MODEL}, {ApiConfig.BASE_URL},
            {ApiConfig.API_KEY}, {ApiConfig.CONTEXT}, {ApiConfig.MAX_OUTPUT_TOKENS},
            {ApiConfig.DESCRIPTION}, {ApiConfig.CREATED_DATE}, {ApiConfig.MODIFIED_DATE}, {ApiConfig.USER_ID}
            FROM {ApiConfig.TABLE_NAME} WHERE {ApiConfig.ID} = $1 AND {ApiConfig.USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (api_id, user_id))
        except Exception as e:
            logger.error(
                f"Error getting API key by ID {api_id} for user {user_id}: {e}"
            )
            return None

    async def get_all(self, user_id: int) -> List[asyncpg.Record]:
        """Gets all API keys for a specific user as asyncpg.Record objects."""
        query_str = f"""
            SELECT {ApiConfig.ID}, {ApiConfig.MODEL}, {ApiConfig.BASE_URL},
            {ApiConfig.API_KEY}, {ApiConfig.CONTEXT}, {ApiConfig.MAX_OUTPUT_TOKENS},
            {ApiConfig.DESCRIPTION}, {ApiConfig.CREATED_DATE}, {ApiConfig.MODIFIED_DATE}, {ApiConfig.USER_ID}
            FROM {ApiConfig.TABLE_NAME}
            WHERE {ApiConfig.USER_ID} = $1
            ORDER BY {ApiConfig.MODEL}
        """
        try:
            return await self._fetchall(query_str, (user_id,))
        except Exception as e:
            logger.error(f"Error getting all API keys for user {user_id}: {e}")
            return []

    async def get_api_count(self, user_id: int) -> int:
        """Gets the total count of API keys for a specific user."""
        query_str = f"SELECT COUNT(*) FROM {ApiConfig.TABLE_NAME} WHERE {ApiConfig.USER_ID} = $1"
        try:
            count = await self._fetchval(query_str, (user_id,))
            return count if count is not None else 0
        except Exception as e:
            logger.error(f"Error getting API key count for user {user_id}: {e}")
            return 0
