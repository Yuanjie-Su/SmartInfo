#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API Key Repository Module (Async)
Provides data access operations for api_config table
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

# Using aiosqlite types if needed, but base repo handles connection
# import aiosqlite

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class ApiKeyRepository(BaseRepository):
    """Repository for api_config table operations (async)."""

    async def save_key(self, api_name: str, api_key: str) -> bool: # Changed to async def
        """Saves or updates an API key."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO api_config (api_name, api_key, created_date, modified_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_name) DO UPDATE SET
                api_key = excluded.api_key,
                modified_date = excluded.modified_date
        """
        # Execute and get cursor (mainly for error checking)
        cursor = await self._execute(query, (api_name, api_key, now, now), commit=True) # Added await
        saved = cursor is not None # Simple check if execute succeeded
        if saved:
            logger.info(f"Saved/Updated API key for '{api_name}'.")
        # Ensure cursor is closed if needed, though _execute might handle it
        # if cursor: await cursor.close() # Add if needed based on BaseRepo impl.
        return saved

    async def get_key(self, api_name: str) -> Optional[str]: # Changed to async def
        """Gets an API key by name."""
        query = "SELECT api_key FROM api_config WHERE api_name = ?"
        result = await self._fetchone(query, (api_name,)) # Added await
        return result[0] if result else None

    async def delete_key(self, api_name: str) -> bool: # Changed to async def
        """Deletes an API key."""
        query = "DELETE FROM api_config WHERE api_name = ?"
        cursor = await self._execute(query, (api_name,), commit=True) # Added await
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted API key for '{api_name}'.")
        # if cursor: await cursor.close() # Add if needed
        return deleted

    async def get_all_keys_info(self) -> List[Tuple[str, str, str]]: # Changed to async def
        """Gets info (name, created, modified) for all keys."""
        query = "SELECT api_name, created_date, modified_date FROM api_config"
        return await self._fetchall(query) # Added await

    async def delete_all(self) -> bool:
        """Deletes all API keys and resets sequence."""
        logger.warning("Attempting to clear all API keys.")
        # Reset auto-increment first (commited by the next statement)
        await self._execute("DELETE FROM sqlite_sequence WHERE name='api_config'", commit=False)
        # Delete all rows
        cursor = await self._execute("DELETE FROM api_config", commit=True) # Added await
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from api_config table and reset sequence.")
        # if cursor: await cursor.close() # Add if needed
        return cleared