#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API Key Repository Module
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from src.db.schema_constants import API_CONFIG_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class ApiKeyRepository(BaseRepository):
    """Repository for api_config table operations."""

    def save_key(self, api_name: str, api_key: str) -> bool:
        """Saves or updates an API key."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = f"""
            INSERT INTO {API_CONFIG_TABLE} (api_name, api_key, created_date, modified_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_name) DO UPDATE SET
                api_key = excluded.api_key,
                modified_date = excluded.modified_date
        """
        cursor = self._execute(query, (api_name, api_key, now, now), commit=True)
        saved = cursor is not None
        if saved:
            logger.info(f"Saved/Updated API key for '{api_name}'.")
        return saved

    def get_key(self, api_name: str) -> Optional[str]:
        """Gets an API key by name."""
        query = f"SELECT api_key FROM {API_CONFIG_TABLE} WHERE api_name = ?"
        result = self._fetchone(query, (api_name,))
        return result[0] if result else None

    def delete_key(self, api_name: str) -> bool:
        """Deletes an API key."""
        query = f"DELETE FROM {API_CONFIG_TABLE} WHERE api_name = ?"
        cursor = self._execute(query, (api_name,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted API key for '{api_name}'.")
        return deleted

    def get_all_keys_info(self) -> List[Tuple[str, str, str]]:
        """Gets info (name, created, modified) for all keys."""
        query = f"SELECT api_name, created_date, modified_date FROM {API_CONFIG_TABLE}"
        return self._fetchall(query)

    def delete_all(self) -> bool:
        """Deletes all API keys."""
        logger.warning("Attempting to clear all API keys.")
        cursor_del = self._execute(f"DELETE FROM {API_CONFIG_TABLE}", commit=False)
        cursor_seq = self._execute(f"DELETE FROM sqlite_sequence WHERE name='{API_CONFIG_TABLE}'", commit=True)
        cleared = cursor_del is not None and cursor_seq is not None
        if cleared:
            logger.info(f"Cleared all data from {API_CONFIG_TABLE} table.")
        else:
            logger.error(f"Failed to clear API keys from {API_CONFIG_TABLE}.")
        return cleared 