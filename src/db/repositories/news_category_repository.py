#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module
"""

import logging
from typing import List, Optional, Tuple

from src.db.schema_constants import NEWS_CATEGORY_TABLE, NEWS_SOURCES_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query = f"INSERT OR IGNORE INTO {NEWS_CATEGORY_TABLE} (name) VALUES (?)"
        cursor = self._execute(query, (name,), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added news category '{name}' with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = self.get_by_name(name)
            # Assuming get_by_name returns (id, name) or None
            return existing[0] if existing else None
        return None

    def get_by_id(self, category_id: int) -> Optional[Tuple[int, str]]:
        """Gets a category by its ID."""
        query = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"
        return self._fetchone(query, (category_id,))

    def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE name = ?"
        return self._fetchone(query, (name,))

    def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} ORDER BY name"
        return self._fetchall(query)

    def update(self, category_id: int, new_name: str) -> bool:
        """Updates a category's name."""
        query = f"UPDATE {NEWS_CATEGORY_TABLE} SET name = ? WHERE id = ?"
        cursor = self._execute(query, (new_name, category_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated category ID {category_id} to name '{new_name}'.")
        return updated

    def delete(self, category_id: int) -> bool:
        """Deletes a category (and cascades to news_sources)."""
        # Note: CASCADE DELETE is handled by DB schema if defined correctly
        query = f"DELETE FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"
        cursor = self._execute(query, (category_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted category ID {category_id} (cascade may apply).")
        return deleted
    
    def delete_all(self) -> bool:
        """Deletes all news categories."""
        cursor_del = self._execute(f"DELETE FROM {NEWS_CATEGORY_TABLE}", commit=False)
        cursor_seq = self._execute(f"DELETE FROM sqlite_sequence WHERE name='{NEWS_CATEGORY_TABLE}'", commit=True)
        deleted = cursor_del is not None and cursor_seq is not None
        if deleted:
            logger.info(f"Cleared all data from {NEWS_CATEGORY_TABLE} table.")
        else:
            logger.error(f"Failed to clear news categories from {NEWS_CATEGORY_TABLE}.")
        return deleted

    def get_with_source_count(self) -> List[Tuple[int, str, int]]:
        """Gets all categories with the count of associated news sources."""
        query = f"""
             SELECT nc.id, nc.name, COUNT(ns.id)
             FROM {NEWS_CATEGORY_TABLE} nc
             LEFT JOIN {NEWS_SOURCES_TABLE} ns ON nc.id = ns.category_id
             GROUP BY nc.id, nc.name
             ORDER BY nc.name
         """
        return self._fetchall(query) 