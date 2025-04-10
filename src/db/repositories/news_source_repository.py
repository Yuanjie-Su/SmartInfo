#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module
"""

import logging
from typing import List, Optional, Tuple

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new news source."""
        query = "INSERT OR IGNORE INTO news_sources (name, url, category_id) VALUES (?, ?, ?)"
        cursor = self._execute(query, (name, url, category_id), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(
                f"Added news source '{name}' ({url}) under category ID {category_id}."
            )
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = self.get_by_url(url)
            # Assuming get_by_url returns (id, name, url, category_id) or None
            return existing[0] if existing else None
        return None

    def get_by_id(self, source_id: int) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its ID."""
        query = "SELECT id, name, url, category_id FROM news_sources WHERE id = ?"
        return self._fetchone(query, (source_id,))

    def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query = "SELECT id, name, url, category_id FROM news_sources WHERE url = ?"
        return self._fetchone(query, (url,))

    def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query = """
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM news_sources ns
            JOIN news_category nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query)

    def get_by_category(self, category_id: int) -> List[Tuple[int, str, str]]:
        """Gets all sources for a specific category ID."""
        query = (
            "SELECT id, name, url FROM news_sources WHERE category_id = ? ORDER BY name"
        )
        return self._fetchall(query, (category_id,))

    def update(self, source_id: int, name: str, url: str, category_id: int) -> bool:
        """Updates an existing news source."""
        query = (
            "UPDATE news_sources SET name = ?, url = ?, category_id = ? WHERE id = ?"
        )
        cursor = self._execute(query, (name, url, category_id, source_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated news source ID {source_id}.")
        return updated

    def delete(self, source_id: int) -> bool:
        """Deletes a news source."""
        query = "DELETE FROM news_sources WHERE id = ?"
        cursor = self._execute(query, (source_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news source ID {source_id}.")
        return deleted 