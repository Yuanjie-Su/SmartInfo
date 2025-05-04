#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

from db.schema_constants import (
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_CATEGORY_ID,
    NEWS_CATEGORY_NAME,
    NEWS_SOURCE_CATEGORY_ID,
)
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    async def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or existing ID if conflict."""
        query_insert = f"""
            INSERT INTO {NEWS_CATEGORY_TABLE} ({NEWS_CATEGORY_NAME}) VALUES ($1)
            ON CONFLICT ({NEWS_CATEGORY_NAME}) DO NOTHING
            RETURNING {NEWS_CATEGORY_ID}
        """
        query_select = f"SELECT {NEWS_CATEGORY_ID} FROM {NEWS_CATEGORY_TABLE} WHERE {NEWS_CATEGORY_NAME} = $1"

        try:
            # Use _fetchone for RETURNING id
            record = await self._fetchone(query_insert, (name,))
            inserted_id = record[0] if record else None

            if inserted_id is not None:
                logger.info(f"Added news category '{name}' with ID {inserted_id}.")
                return inserted_id
            else:
                logger.debug(f"Category '{name}' likely already exists. Fetching ID.")
                # Use _fetchone for SELECT id
                existing_record = await self._fetchone(query_select, (name,))
                existing_id = existing_record[0] if existing_record else None
                if existing_id is not None:
                    logger.debug(
                        f"Found existing category '{name}' with ID {existing_id}."
                    )
                    return existing_id
                else:
                    logger.error(
                        f"Category '{name}' conflict occurred but failed to fetch existing ID."
                    )
                    return None

        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news category: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding news category: {e}")
            return None

    async def get_by_id(self, category_id: int) -> Optional[asyncpg.Record]:
        """Gets a category by its ID."""
        query_str = f"SELECT {NEWS_CATEGORY_ID}, {NEWS_CATEGORY_NAME} FROM {NEWS_CATEGORY_TABLE} WHERE {NEWS_CATEGORY_ID} = $1"

        try:
            return await self._fetchone(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting category by ID: {e}")
            return None

    async def get_by_name(self, name: str) -> Optional[asyncpg.Record]:
        """Gets a category by its name."""
        query_str = f"SELECT {NEWS_CATEGORY_ID}, {NEWS_CATEGORY_NAME} FROM {NEWS_CATEGORY_TABLE} WHERE {NEWS_CATEGORY_NAME} = $1"

        try:
            return await self._fetchone(query_str, (name,))
        except Exception as e:
            logger.error(f"Error getting category by name: {e}")
            return None

    async def exists_by_name(self, name: str) -> bool:
        """Checks if a category with the given name exists."""
        query_str = f"SELECT 1 FROM {NEWS_CATEGORY_TABLE} WHERE {NEWS_CATEGORY_NAME} = $1 LIMIT 1"
        try:
            # Use _fetchone
            record = await self._fetchone(query_str, (name,))
            return record is not None
        except Exception as e:
            logger.error(f"Error checking if category exists by name: {e}")
            return False

    async def get_all(self) -> List[asyncpg.Record]:
        """Gets all categories."""
        query_str = f"SELECT {NEWS_CATEGORY_ID}, {NEWS_CATEGORY_NAME} FROM {NEWS_CATEGORY_TABLE} ORDER BY {NEWS_CATEGORY_NAME}"

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting all categories: {e}")
            return []

    async def get_with_source_count(self) -> List[asyncpg.Record]:
        """Gets all categories with count of sources for each category."""
        query_str = f"""
            SELECT c.{NEWS_CATEGORY_ID}, c.{NEWS_CATEGORY_NAME}, COUNT(s.id) as source_count
            FROM {NEWS_CATEGORY_TABLE} c
            LEFT JOIN {NEWS_SOURCES_TABLE} s ON c.{NEWS_CATEGORY_ID} = s.{NEWS_SOURCE_CATEGORY_ID}
            GROUP BY c.{NEWS_CATEGORY_ID}, c.{NEWS_CATEGORY_NAME}
            ORDER BY c.{NEWS_CATEGORY_NAME}
        """

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting categories with source count: {e}")
            return []

    async def update(self, category_id: int, name: str) -> bool:
        """Updates a category by ID."""
        query_str = f"UPDATE {NEWS_CATEGORY_TABLE} SET {NEWS_CATEGORY_NAME} = $1 WHERE {NEWS_CATEGORY_ID} = $2"

        try:
            status = await self._execute(query_str, (name, category_id))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated category ID {category_id} to '{name}'.")
            else:
                logger.warning(
                    f"Update command for category ID {category_id} executed but status was '{status}'."
                )
            return updated
        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error updating category (potential duplicate name '{name}'): {e}"
            )
            return False
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating category: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating category: {e}")
            return False

    async def delete(self, category_id: int) -> bool:
        """Deletes a category by ID."""
        query_str = f"DELETE FROM {NEWS_CATEGORY_TABLE} WHERE {NEWS_CATEGORY_ID} = $1"

        try:
            status = await self._execute(query_str, (category_id,))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted category ID {category_id}.")
            else:
                logger.warning(
                    f"Delete command for category ID {category_id} executed but status was '{status}'."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting category {category_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting category: {e}")
            return False
