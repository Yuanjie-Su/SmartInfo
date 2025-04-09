#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module
"""

import logging
from typing import List, Optional, Tuple

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query = "INSERT OR IGNORE INTO news_category (name) VALUES (?)"
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
        query = "SELECT id, name FROM news_category WHERE id = ?"
        return self._fetchone(query, (category_id,))

    def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query = "SELECT id, name FROM news_category WHERE name = ?"
        return self._fetchone(query, (name,))

    def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query = "SELECT id, name FROM news_category ORDER BY name"
        return self._fetchall(query)

    def update(self, category_id: int, new_name: str) -> bool:
        """Updates a category's name."""
        query = "UPDATE news_category SET name = ? WHERE id = ?"
        cursor = self._execute(query, (new_name, category_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated category ID {category_id} to name '{new_name}'.")
        return updated

    def delete(self, category_id: int) -> bool:
        """Deletes a category (and cascades to news_sources)."""
        # Note: CASCADE DELETE is handled by DB schema if defined correctly
        query = "DELETE FROM news_category WHERE id = ?"
        cursor = self._execute(query, (category_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted category ID {category_id} (cascade may apply).")
        return deleted

    def get_with_source_count(self) -> List[Tuple[int, str, int]]:
        """Gets all categories with the count of associated news sources."""
        query = """
             SELECT nc.id, nc.name, COUNT(ns.id)
             FROM news_category nc
             LEFT JOIN news_sources ns ON nc.id = ns.category_id
             GROUP BY nc.id, nc.name
             ORDER BY nc.name
         """
        return self._fetchall(query) 