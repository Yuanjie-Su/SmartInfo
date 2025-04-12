#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module (Async)
Provides data access operations for news_category table
"""

import logging
from typing import List, Optional, Tuple

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    async def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query = "INSERT OR IGNORE INTO news_category (name) VALUES (?)"
        cursor = await self._execute(query, (name,), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added news category '{name}' with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = await self.get_by_name(name)
            # Assuming get_by_name returns (id, name) or None
            return existing[0] if existing else None
        return None

    async def get_by_id(self, category_id: int) -> Optional[Tuple[int, str]]:
        """Gets a category by its ID."""
        query = "SELECT id, name FROM news_category WHERE id = ?"
        return await self._fetchone(query, (category_id,))

    async def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query = "SELECT id, name FROM news_category WHERE name = ?"
        return await self._fetchone(query, (name,))

    async def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query = "SELECT id, name FROM news_category ORDER BY name"
        return await self._fetchall(query)

    async def update(self, category_id: int, new_name: str) -> bool:
        """Updates a category's name."""
        query = "UPDATE news_category SET name = ? WHERE id = ?"
        cursor = await self._execute(query, (new_name, category_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated category ID {category_id} to name '{new_name}'.")
        return updated

    async def delete(self, category_id: int) -> bool:
        """Deletes a category (and cascades to news_sources)."""
        # Note: CASCADE DELETE is handled by DB schema if defined correctly
        query = "DELETE FROM news_category WHERE id = ?"
        cursor = await self._execute(query, (category_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted category ID {category_id} (cascade may apply).")
        return deleted
    
    async def delete_all(self) -> bool:
        """Deletes all news categories and resets sequence."""
        logger.warning("Attempting to clear all news categories.")
         # Reset auto-increment first
        await self._execute("DELETE FROM sqlite_sequence WHERE name='news_category'", commit=False)
        cursor = await self._execute("DELETE FROM news_category", commit=True)
        deleted = cursor is not None # Check if execute succeeded
        if deleted:
            logger.info("Cleared all data from news_category table and reset sequence.")
        return deleted
