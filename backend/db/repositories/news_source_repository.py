#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module (Async)
Provides data access operations for news_sources table
"""

import logging
import sqlite3
from typing import List, Optional, Tuple

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    async def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new news source."""
        query = "INSERT OR IGNORE INTO news_sources (name, url, category_id) VALUES (?, ?, ?)"
        cursor = await self._execute(query, (name, url, category_id), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(
                f"Added news source '{name}' ({url}) under category ID {category_id}."
            )
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = await self.get_by_url(url)
            # Assuming get_by_url returns (id, name, url, category_id) or None
            return existing[0] if existing else None
        return None

    async def get_by_id(self, source_id: int) -> Optional[Tuple[int, str, str, int, str]]:
        """Gets a source by its ID."""
        query = """
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name AS category_name
            FROM news_sources ns
            JOIN news_category nc
            ON ns.category_id = nc.id
            WHERE ns.id = ?  
        """
        try:
            return await self._fetchone(query, (source_id,))
        except sqlite3.Error as db_err:
            logger.error(f"Database error in get_by_id for source ID {source_id}: {db_err}", exc_info=True)
            raise db_err  # Or wrap in a custom exception

    async def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query = "SELECT id, name, url, category_id FROM news_sources WHERE url = ?"
        return await self._fetchone(query, (url,))

    async def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query = """
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM news_sources ns
            JOIN news_category nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """
        # Ensure the BaseRepository's _fetchall handles potential DB errors gracefully too
        try:
            return await self._fetchall(query)
        except sqlite3.Error as db_err:
             logger.error(f"Database error in get_all sources: {db_err}", exc_info=True)
             # Re-raise or return empty list, depending on desired error handling
             # Raising allows the service/router to catch it.
             raise db_err # Or wrap in a custom exception

    async def get_by_category(self, category_id: int) -> List[Tuple[int, str, str]]:
        """Gets all sources for a specific category ID."""
        query = (
            "SELECT id, name, url FROM news_sources WHERE category_id = ? ORDER BY name"
        )
        return await self._fetchall(query, (category_id,))

    async def update(self, source_id: int, name: str, url: str, category_id: int) -> bool:
        """Updates an existing news source."""
        query = (
            "UPDATE news_sources SET name = ?, url = ?, category_id = ? WHERE id = ?"
        )
        cursor = await self._execute(query, (name, url, category_id, source_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated news source ID {source_id}.")
        return updated

    async def delete(self, source_id: int) -> bool:
        """Deletes a news source."""
        query = "DELETE FROM news_sources WHERE id = ?"
        cursor = await self._execute(query, (source_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news source ID {source_id}.")
        return deleted
    
    async def delete_all(self) -> bool:
        """Deletes all news sources and resets sequence."""
        logger.warning("Attempting to clear all news sources.")
        # Reset auto-increment first
        await self._execute("DELETE FROM sqlite_sequence WHERE name='news_sources'", commit=False)
        cursor = await self._execute("DELETE FROM news_sources", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from news_sources table and reset sequence.")
        return cleared