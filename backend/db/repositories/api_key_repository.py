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
    API_CONFIG_NAME,
    API_CONFIG_API_KEY,
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
        self, api_name: str, api_key: str, description: str = None
    ) -> Optional[int]:
        """Adds a new API key configuration. Returns new ID or None if failed/exists."""
        if await self.get_by_name(api_name) is not None:
            logger.debug(f"API key for {api_name} already exists, updating instead.")
            return None

        current_time = int(time.time())
        query_str = f"""
            INSERT INTO {API_CONFIG_TABLE} (
                {API_CONFIG_NAME}, {API_CONFIG_API_KEY}, {API_CONFIG_DESCRIPTION},
                {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE}
            ) VALUES (?, ?, ?, ?, ?)
        """

        try:
            cursor = await self._execute(
                query_str,
                (api_name, api_key, description, current_time, current_time),
                commit=True,
            )
            last_id = self._get_last_insert_id(cursor)
            if last_id:
                logger.info(f"Added API key for {api_name} with ID {last_id}.")
            return last_id
        except Exception as e:
            logger.error(f"Error adding API key: {e}")
            return None

    async def update(
        self, api_id: int, api_key: str = None, description: str = None
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
            SET {API_CONFIG_API_KEY} = ?, {API_CONFIG_DESCRIPTION} = ?, {API_CONFIG_MODIFIED_DATE} = ?
            WHERE {API_CONFIG_ID} = ?
        """

        try:
            cursor = await self._execute(
                query_str,
                (
                    api_key if api_key is not None else existing[2],
                    description if description is not None else existing[3],
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

    async def update_by_name(
        self, api_name: str, api_key: str, description: str = None
    ) -> bool:
        """Updates an API key by name. Creates it if it doesn't exist."""
        existing = await self.get_by_name(api_name)

        if existing:
            # Update existing
            api_id = existing[0]
            current_time = int(time.time())
            query_str = f"""
                UPDATE {API_CONFIG_TABLE} 
                SET {API_CONFIG_API_KEY} = ?, {API_CONFIG_DESCRIPTION} = ?, {API_CONFIG_MODIFIED_DATE} = ?
                WHERE {API_CONFIG_ID} = ?
            """
            try:
                cursor = await self._execute(
                    query_str, (api_key, description, current_time, api_id), commit=True
                )
                updated = self._get_rows_affected(cursor) > 0
                if updated:
                    logger.info(f"Updated API key for {api_name}.")
                return updated
            except Exception as e:
                logger.error(f"Error updating API key by name: {e}")
                return False
        else:
            # Create new
            new_id = await self.add(api_name, api_key, description)
            return new_id is not None

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

    async def get_by_id(
        self, api_id: int
    ) -> Optional[Tuple[int, str, str, str, str, str]]:
        """Gets an API key by ID."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_NAME}, {API_CONFIG_API_KEY}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_ID} = ?
        """

        try:
            return await self._fetchone(query_str, (api_id,))
        except Exception as e:
            logger.error(f"Error getting API key by ID: {e}")
            return None

    async def get_by_name(
        self, api_name: str
    ) -> Optional[Tuple[int, str, str, str, str, str]]:
        """Gets an API key by name."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_NAME}, {API_CONFIG_API_KEY}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} WHERE {API_CONFIG_NAME} = ?
        """

        try:
            return await self._fetchone(query_str, (api_name,))
        except Exception as e:
            logger.error(f"Error getting API key by name: {e}")
            return None

    async def get_all(self) -> List[Dict[str, Any]]:
        """Gets all API keys as dictionaries."""
        query_str = f"""
            SELECT {API_CONFIG_ID}, {API_CONFIG_NAME}, {API_CONFIG_API_KEY}, 
            {API_CONFIG_DESCRIPTION}, {API_CONFIG_CREATED_DATE}, {API_CONFIG_MODIFIED_DATE} 
            FROM {API_CONFIG_TABLE} ORDER BY {API_CONFIG_NAME}
        """

        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting all API keys: {e}")
            return []
