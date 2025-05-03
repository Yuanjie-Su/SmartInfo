#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any

from db.schema_constants import NEWS_CATEGORY_TABLE, NEWS_SOURCES_TABLE
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    async def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query_str = f"INSERT OR IGNORE INTO {NEWS_CATEGORY_TABLE} (name) VALUES (?)"

        try:
            cursor = await self._execute(query_str, (name,), commit=True)

            # Check if insert happened or row existed
            if self._get_rows_affected(cursor) > 0:
                last_id = self._get_last_insert_id(cursor)
                if last_id:
                    logger.info(f"Added news category '{name}' with ID {last_id}.")
                    return last_id
                else:
                    # Insert happened but ID retrieval failed (shouldn't usually happen)
                    logger.warning(f"Category '{name}' added but failed to get ID.")
                    return None
            else:
                # INSERT IGNORE: Row likely existed, fetch its ID
                logger.debug(f"Category '{name}' likely already exists. Fetching ID.")
                existing = await self.get_by_name(name)
                return existing[0] if existing else None
        except Exception as e:
            logger.error(f"Error adding news category: {e}")
            return None

    async def get_by_id(self, category_id: int) -> Optional[Tuple[int, str]]:
        """Gets a category by its ID."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"

        try:
            return await self._fetchone(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting category by ID: {e}")
            return None

    async def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE name = ?"

        try:
            return await self._fetchone(query_str, (name,))
        except Exception as e:
            logger.error(f"Error getting category by name: {e}")
            return None

    async def exists_by_name(self, name: str) -> bool:
        """Checks if a category with the given name exists."""
        result = await self.get_by_name(name)
        return result is not None

    async def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} ORDER BY name"

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting all categories: {e}")
            return []

    async def get_with_source_count(self) -> List[Tuple[int, str, int]]:
        """Gets all categories with count of sources for each category."""
        query_str = f"""
            SELECT c.id, c.name, COUNT(s.id) as source_count
            FROM {NEWS_CATEGORY_TABLE} c
            LEFT JOIN {NEWS_SOURCES_TABLE} s ON c.id = s.category_id
            GROUP BY c.id, c.name
            ORDER BY c.name
        """

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting categories with source count: {e}")
            return []

    async def update(self, category_id: int, name: str) -> bool:
        """Updates a category by ID."""
        query_str = f"UPDATE {NEWS_CATEGORY_TABLE} SET name = ? WHERE id = ?"

        try:
            cursor = await self._execute(query_str, (name, category_id), commit=True)
            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated category ID {category_id} to '{name}'.")
            return updated
        except Exception as e:
            logger.error(f"Error updating category: {e}")
            return False

    async def delete(self, category_id: int) -> bool:
        """Deletes a category by ID."""
        query_str = f"DELETE FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"

        try:
            cursor = await self._execute(query_str, (category_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0
            if deleted:
                logger.info(f"Deleted category ID {category_id}.")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting category: {e}")
            return False

    async def get_all_as_dict(self) -> List[dict]:
        """Gets all categories as dictionaries."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} ORDER BY name"

        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting all categories as dict: {e}")
            return []

    async def get_with_source_count_as_dict(self) -> List[dict]:
        """Gets all categories with count of sources for each category as dictionaries."""
        query_str = f"""
            SELECT c.id, c.name, COUNT(s.id) as source_count
            FROM {NEWS_CATEGORY_TABLE} c
            LEFT JOIN {NEWS_SOURCES_TABLE} s ON c.id = s.category_id
            GROUP BY c.id, c.name
            ORDER BY c.name
        """

        try:
            return await self._fetch_as_dict(query_str)
        except Exception as e:
            logger.error(f"Error getting categories with source count as dict: {e}")
            return []

    async def get_by_id_as_dict(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Gets a category by its ID as a dictionary.

        Args:
            category_id: ID of the category to retrieve

        Returns:
            Dictionary with category data or None if not found
        """
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"

        try:
            return await self._fetchone_as_dict(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting category by ID as dict: {e}")
            return None
