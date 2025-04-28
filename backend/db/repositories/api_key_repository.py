#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API Key Repository Module
Provides data access operations for API keys
"""

import logging
import time
from typing import List, Optional, Tuple, Dict, Any, Union
import sqlite3

from backend.db.schema_constants import (
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
from backend.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ApiKeyRepository(BaseRepository):
    """Repository for API key management operations."""

    def __init__(self, connection: Optional[sqlite3.Connection] = None):
        """Initialize with optional database connection for testing."""
        super().__init__(connection=connection)

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
        current_time = int(time.time())
        query_str = f"""
            INSERT INTO {API_CONFIG_TABLE} (
                {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, {API_CONFIG_API_KEY}, 
                {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, {API_CONFIG_DESCRIPTION},
                {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE}
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            cursor = await self._execute(
                query_str,
                (
                    model,
                    base_url,
                    api_key,
                    context,
                    max_output_tokens,
                    description,
                    current_time,
                    current_time,
                ),
                commit=True,
            )
            last_id = self._get_last_insert_id(cursor)
            if last_id:
                logger.info(f"Added API key for model {model} with ID {last_id}.")
            return last_id
        except Exception as e:
            logger.error(f"Error adding API key: {e}")
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
        # Get current values
        existing = await self.get_by_id(api_id)
        if not existing:
            logger.warning(f"Failed to update API key ID {api_id} (not found).")
            return False

        current_time = int(time.time())
        query_str = f"""
            UPDATE {API_CONFIG_TABLE} 
            SET {API_CONFIG_MODEL} = ?, {API_CONFIG_BASE_URL} = ?, 
                {API_CONFIG_API_KEY} = ?, {API_CONFIG_CONTEXT} = ?, 
                {API_CONFIG_MAX_OUTPUT_TOKENS} = ?, {API_CONFIG_DESCRIPTION} = ?, 
                {API_CONFIG_MODIFIED_DATE} = ?
            WHERE {API_CONFIG_ID} = ?
        """

        try:
            cursor = await self._execute(
                query_str,
                (
                    model,
                    base_url,
                    api_key if api_key is not None else existing[3],
                    context if context is not None else existing[4],
                    max_output_tokens if max_output_tokens is not None else existing[5],
                    description if description is not None else existing[6],
                    current_time,
                    api_id,
                ),
                commit=True,
            )
            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated API key ID {api_id}.")
            return updated
        except Exception as e:
            logger.error(f"Error updating API key: {e}")
            return False

    async def delete(self, api_id: int) -> bool:
        """Deletes an API key by ID."""
        query_str = f"DELETE FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_ID} = ?"

        try:
            cursor = await self._execute(query_str, (api_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0
            if deleted:
                logger.info(f"Deleted API key ID {api_id}.")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting API key: {e}")
            return False

    async def get_by_id(self, api_id: int) -> Optional[Tuple]:
        """Gets an API key by ID."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, 
            {API_CONFIG_API_KEY}, {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_ID} = ?
        """

        try:
            return await self._fetchone(query_str, (api_id,))
        except Exception as e:
            logger.error(f"Error getting API key by ID: {e}")
            return None

    async def get_all(self) -> List[Dict[str, Any]]:
        """Gets all API keys as dictionaries."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_MODEL}, {API_CONFIG_BASE_URL}, 
            {API_CONFIG_API_KEY}, {API_CONFIG_CONTEXT}, {API_CONFIG_MAX_OUTPUT_TOKENS}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} ORDER BY {API_CONFIG_MODEL}
        """

        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting all API keys: {e}")
            return []
