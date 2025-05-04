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


from db.schema_constants import (
    API_CONFIG_TABLE,
    API_CONFIG_ID,
    API_CONFIG_MODEL,
    API_CONFIG_BASE_URL,
    API_CONFIG_API_KEY,
    API_CONFIG_CONTEXT,
    API_CONFIG_MAX_OUTPUT_TOKENS,
    API_CONFIG_DESCRIPTION,
    API_CONFIG_CREATED_DATE,
    API_CONFIG_MODIFIED_DATE,
)
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
        description: str = None,
    ) -> Optional[int]:
        """Adds a new API key configuration. Returns new ID or None if failed."""
        current_time = datetime.now(timezone.utc)
        query_str = f"""
            INSERT INTO {API_CONFIG_TABLE} (
                {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, {API_CONFIG_API_KEY}, 
                {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, {API_CONFIG_DESCRIPTION},
                {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING {API_CONFIG_ID}
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
        )

        try:
            # Use _fetchval for RETURNING id
            last_id = await self._fetchval(query_str, params)

            if last_id is not None:
                logger.info(f"Added API key for model {model} with ID {last_id}.")
            else:
                logger.warning(
                    f"Failed to add API key for model {model}, no ID returned."
                )
            return last_id
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding API key: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding API key: {e}")
            return None

    async def update(
        self,
        api_id: int,
        model: str,
        base_url: str,
        api_key: str = None,
        context: int = None,
        max_output_tokens: int = None,
        description: str = None,
    ) -> bool:
        """Updates an API key by ID."""
        existing_record = await self.get_by_id(api_id)
        if not existing_record:
            logger.warning(f"Failed to update API key ID {api_id} (not found).")
            return False
        existing = dict(existing_record)

        current_time = datetime.now(timezone.utc)
        query_str = f"""
            UPDATE {API_CONFIG_TABLE} 
            SET {API_CONFIG_MODEL} = $1, {API_CONFIG_BASE_URL} = $2, 
                {API_CONFIG_API_KEY} = $3, {API_CONFIG_CONTEXT} = $4, 
                {API_CONFIG_MAX_OUTPUT_TOKENS} = $5, {API_CONFIG_DESCRIPTION} = $6, 
                {API_CONFIG_MODIFIED_DATE} = $7
            WHERE {API_CONFIG_ID} = $8
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
                else existing[API_CONFIG_DESCRIPTION.lower()]
            ),
            current_time,
            api_id,
        )

        try:
            status = await self._execute(query_str, params)
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated API key ID {api_id}.")
            else:
                logger.warning(
                    f"Update command for API key ID {api_id} executed but status was '{status}'."
                )
            return updated
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating API key: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating API key: {e}")
            return False

    async def delete(self, api_id: int) -> bool:
        """Deletes an API key by ID."""
        query_str = f"DELETE FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_ID} = $1"

        try:
            status = await self._execute(query_str, (api_id,))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted API key ID {api_id}.")
            else:
                logger.warning(
                    f"Delete command for API key ID {api_id} executed but status was '{status}'."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting API key: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting API key: {e}")
            return False

    async def get_by_id(self, api_id: int) -> Optional[asyncpg.Record]:
        """Gets an API key by ID."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, 
            {API_CONFIG_API_KEY}, {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_ID} = $1
        """

        try:
            return await self._fetchone(query_str, (api_id,))
        except Exception as e:
            logger.error(f"Error getting API key by ID: {e}")
            return None

    async def get_all(self) -> List[asyncpg.Record]:
        """Gets all API keys as asyncpg.Record objects."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, 
            {API_CONFIG_API_KEY}, {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} ORDER BY {API_CONFIG_MODEL}
        """

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting all API keys: {e}")
            return []

    async def get_api_count(self) -> int:
        """Gets the total count of API keys."""
        query_str = f"SELECT COUNT(*) FROM {API_CONFIG_TABLE}"

        try:
            count = await self._fetchval(query_str)
            return count if count is not None else 0
        except Exception as e:
            logger.error(f"Error getting API key count: {e}")
            return 0
