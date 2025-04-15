#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module
"""

import logging
from typing import List, Optional, Tuple

from src.db.schema_constants import NEWS_SOURCES_TABLE, NEWS_CATEGORY_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new news source."""
        query = f"INSERT OR IGNORE INTO {NEWS_SOURCES_TABLE} (name, url, category_id) VALUES (?, ?, ?)"
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
        query = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE id = ?"
        )
        return self._fetchone(query, (source_id,))

    def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE url = ?"
        )
        return self._fetchone(query, (url,))

    def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query)

    def get_by_category(self, category_id: int) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources for a specific category ID."""
        query = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            WHERE ns.category_id = ?
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query, (category_id,))

    def update(self, source_id: int, name: str, url: str, category_id: int) -> bool:
        """Updates an existing news source."""
        query = f"UPDATE {NEWS_SOURCES_TABLE} SET name = ?, url = ?, category_id = ? WHERE id = ?"
        cursor = self._execute(query, (name, url, category_id, source_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated news source ID {source_id}.")
        else:
            logger.error(f"Failed to update news source ID {source_id}.")
        return updated

    def delete(self, source_id: int) -> bool:
        """Deletes a news source."""
        query = f"DELETE FROM {NEWS_SOURCES_TABLE} WHERE id = ?"
        cursor = self._execute(query, (source_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news source ID {source_id}.")
        else:
            logger.error(f"Failed to delete news source ID {source_id}.")
        return deleted

    def delete_all(self) -> bool:
        """Deletes all news sources."""
        cursor_del = self._execute(f"DELETE FROM {NEWS_SOURCES_TABLE}", commit=False)
        cursor_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_SOURCES_TABLE}'",
            commit=True,
        )
        deleted = cursor_del is not None and cursor_seq is not None
        if deleted:
            logger.info(f"Cleared all data from {NEWS_SOURCES_TABLE} table.")
        else:
            logger.error(f"Failed to clear news sources from {NEWS_SOURCES_TABLE}.")
        return deleted
