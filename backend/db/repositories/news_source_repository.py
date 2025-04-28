#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any

from backend.db.schema_constants import NEWS_SOURCES_TABLE, NEWS_CATEGORY_TABLE
from backend.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    async def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new source. Returns the new ID or None if failed/exists."""
        if await self.exists_by_url(url):
            logger.debug(f"Source with URL {url} already exists.")
            return None

        query_str = f"INSERT INTO {NEWS_SOURCES_TABLE} (name, url, category_id) VALUES (?, ?, ?)"

        try:
            cursor = await self._execute(
                query_str, (name, url, category_id), commit=True
            )
            last_id = self._get_last_insert_id(cursor)
            if last_id:
                logger.info(f"Added news source '{name}' with ID {last_id}.")
            return last_id
        except Exception as e:
            logger.error(f"Error adding news source: {e}")
            return None

    async def update(
        self, source_id: int, name: str, url: str, category_id: int
    ) -> bool:
        """Updates an existing source."""
        query_str = f"""
            UPDATE {NEWS_SOURCES_TABLE} 
            SET name = ?, url = ?, category_id = ? 
            WHERE id = ?
        """

        try:
            cursor = await self._execute(
                query_str, (name, url, category_id, source_id), commit=True
            )
            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated source ID {source_id}.")
            else:
                logger.warning(f"Failed to update source ID {source_id}.")
            return updated
        except Exception as e:
            logger.error(f"Error updating news source: {e}")
            return False

    async def delete(self, source_id: int) -> bool:
        """Deletes a source."""
        query_str = f"DELETE FROM {NEWS_SOURCES_TABLE} WHERE id = ?"

        try:
            cursor = await self._execute(query_str, (source_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0
            if deleted:
                logger.info(f"Deleted source ID {source_id}.")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting news source: {e}")
            return False

    async def get_by_id(self, source_id: int) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its ID."""
        query_str = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE id = ?"
        )

        try:
            return await self._fetchone(query_str, (source_id,))
        except Exception as e:
            logger.error(f"Error getting news source by ID: {e}")
            return None

    async def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query_str = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE url = ?"
        )

        try:
            return await self._fetchone(query_str, (url,))
        except Exception as e:
            logger.error(f"Error getting news source by URL: {e}")
            return None

    async def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting all news sources: {e}")
            return []

    async def get_by_category(
        self, category_id: int
    ) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources for a specific category ID."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            WHERE ns.category_id = ?
            ORDER BY nc.name, ns.name
        """

        try:
            return await self._fetchall(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting news sources by category: {e}")
            return []

    async def exists_by_url(self, url: str) -> bool:
        """Checks if a source exists with the given URL."""
        query_str = f"SELECT 1 FROM {NEWS_SOURCES_TABLE} WHERE url = ? LIMIT 1"

        try:
            row = await self._fetchone(query_str, (url,))
            return row is not None
        except Exception as e:
            logger.error(f"Error checking if news source exists by URL: {e}")
            return False

    async def exists_by_name(self, name: str) -> bool:
        """Checks if a source exists with the given name."""
        query_str = f"SELECT 1 FROM {NEWS_SOURCES_TABLE} WHERE name = ? LIMIT 1"

        try:
            row = await self._fetchone(query_str, (name,))
            return row is not None
        except Exception as e:
            logger.error(f"Error checking if news source exists by name: {e}")
            return False

    async def get_by_id_as_dict(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Gets a source by its ID as a dictionary."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            WHERE ns.id = ?
        """

        try:
            return await self._fetchone_as_dict(query_str, (source_id,))
        except Exception as e:
            logger.error(f"Error getting news source by ID as dict: {e}")
            return None

    async def get_all_as_dict(self) -> List[Dict[str, Any]]:
        """Gets all sources with category names as dictionaries."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """

        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting all news sources as dict: {e}")
            return []

    async def get_by_category_as_dict(self, category_id: int) -> List[Dict[str, Any]]:
        """Gets all sources for a specific category ID as dictionaries."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            WHERE ns.category_id = ?
            ORDER BY nc.name, ns.name
        """

        try:
            return await self._fetch_as_dict(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting news sources by category as dict: {e}")
            return []
