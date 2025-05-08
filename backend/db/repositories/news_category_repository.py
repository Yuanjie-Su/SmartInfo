#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

from db.schema_constants import NewsCategory, NewsSource
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    async def add(self, name: str, user_id: int) -> Optional[int]:
        """Adds a new category for a user. Returns the new ID or existing ID if conflict."""
        query_insert = f"""
            INSERT INTO {NewsCategory.TABLE_NAME} ({NewsCategory.NAME}, {NewsCategory.USER_ID}) VALUES ($1, $2)
            ON CONFLICT ({NewsCategory.NAME}, {NewsCategory.USER_ID}) DO NOTHING
            RETURNING {NewsCategory.ID}
        """
        query_select = f"SELECT {NewsCategory.ID} FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.NAME} = $1 AND {NewsCategory.USER_ID} = $2"
        params_insert = (name, user_id)
        params_select = (name, user_id)

        try:
            record = await self._fetchone(query_insert, params_insert)
            inserted_id = record[0] if record else None

            if inserted_id is not None:
                logger.info(
                    f"Added news category '{name}' with ID {inserted_id} for user {user_id}."
                )
                return inserted_id
            else:
                logger.debug(
                    f"Category '{name}' for user {user_id} likely already exists. Fetching ID."
                )
                existing_record = await self._fetchone(query_select, params_select)
                existing_id = existing_record[0] if existing_record else None
                if existing_id is not None:
                    logger.debug(
                        f"Found existing category '{name}' with ID {existing_id} for user {user_id}."
                    )
                    return existing_id
                else:
                    logger.error(
                        f"Category '{name}' conflict for user {user_id} occurred but failed to fetch existing ID."
                    )
                    return None

        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news category for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error adding news category for user {user_id}: {e}"
            )
            return None

    async def get_by_id(
        self, category_id: int, user_id: int
    ) -> Optional[asyncpg.Record]:
        """Gets a category by its ID for a specific user."""
        query_str = f"SELECT {NewsCategory.ID}, {NewsCategory.NAME}, {NewsCategory.USER_ID} FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.ID} = $1 AND {NewsCategory.USER_ID} = $2"
        try:
            return await self._fetchone(query_str, (category_id, user_id))
        except Exception as e:
            logger.error(
                f"Error getting category by ID {category_id} for user {user_id}: {e}"
            )
            return None

    async def get_by_name(self, name: str, user_id: int) -> Optional[asyncpg.Record]:
        """Gets a category by its name for a specific user."""
        query_str = f"SELECT {NewsCategory.ID}, {NewsCategory.NAME}, {NewsCategory.USER_ID} FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.NAME} = $1 AND {NewsCategory.USER_ID} = $2"
        try:
            return await self._fetchone(query_str, (name, user_id))
        except Exception as e:
            logger.error(
                f"Error getting category by name '{name}' for user {user_id}: {e}"
            )
            return None

    async def exists_by_name(self, name: str, user_id: int) -> bool:
        """Checks if a category with the given name exists for a specific user."""
        query_str = f"SELECT 1 FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.NAME} = $1 AND {NewsCategory.USER_ID} = $2 LIMIT 1"
        try:
            record = await self._fetchone(query_str, (name, user_id))
            return record is not None
        except Exception as e:
            logger.error(
                f"Error checking if category exists by name for user {user_id}: {e}"
            )
            return False

    async def get_all(self, user_id: int) -> List[asyncpg.Record]:
        """Gets all categories for a specific user."""
        query_str = f"SELECT {NewsCategory.ID}, {NewsCategory.NAME}, {NewsCategory.USER_ID} FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.USER_ID} = $1 ORDER BY {NewsCategory.NAME}"
        try:
            return await self._fetchall(query_str, (user_id,))
        except Exception as e:
            logger.error(f"Error getting all categories for user {user_id}: {e}")
            return []

    async def get_with_source_count(self, user_id: int) -> List[asyncpg.Record]:
        """Gets all categories for a user with count of sources (also belonging to the user) for each category."""
        query_str = f"""
            SELECT c.{NewsCategory.ID}, c.{NewsCategory.NAME}, COUNT(s.{NewsSource.ID}) as source_count
            FROM {NewsCategory.TABLE_NAME} c
            LEFT JOIN {NewsSource.TABLE_NAME} s ON c.{NewsCategory.ID} = s.{NewsSource.CATEGORY_ID} AND s.{NewsSource.USER_ID} = c.{NewsCategory.USER_ID}
            WHERE c.{NewsCategory.USER_ID} = $1
            GROUP BY c.{NewsCategory.ID}, c.{NewsCategory.NAME}
            ORDER BY c.{NewsCategory.NAME}
        """
        try:
            return await self._fetchall(query_str, (user_id,))
        except Exception as e:
            logger.error(
                f"Error getting categories with source count for user {user_id}: {e}"
            )
            return []

    async def update(self, category_id: int, user_id: int, name: str) -> bool:
        """Updates a category by ID for a specific user."""
        query_str = f"UPDATE {NewsCategory.TABLE_NAME} SET {NewsCategory.NAME} = $1 WHERE {NewsCategory.ID} = $2 AND {NewsCategory.USER_ID} = $3"
        try:
            status = await self._execute(query_str, (name, category_id, user_id))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(
                    f"Updated category ID {category_id} to '{name}' for user {user_id}."
                )
            else:
                logger.warning(
                    f"Update command for category ID {category_id} (User: {user_id}) executed but status was '{status}'. Category might not exist or belong to user."
                )
            return updated
        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error updating category for user {user_id} (potential duplicate name '{name}'): {e}"
            )
            return False
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating category for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating category for user {user_id}: {e}")
            return False

    async def delete(self, category_id: int, user_id: int) -> bool:
        """Deletes a category by ID for a specific user."""
        # Note: Consider implications if news sources depend on this category.
        # The DB schema should define ON DELETE behavior (e.g., RESTRICT, CASCADE, SET NULL).
        # Assuming RESTRICT or similar, this might fail if sources exist.
        query_str = f"DELETE FROM {NewsCategory.TABLE_NAME} WHERE {NewsCategory.ID} = $1 AND {NewsCategory.USER_ID} = $2"
        try:
            status = await self._execute(query_str, (category_id, user_id))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted category ID {category_id} for user {user_id}.")
            else:
                logger.warning(
                    f"Delete command for category ID {category_id} (User: {user_id}) executed but status was '{status}'. Category might not exist, belong to user, or have dependent sources."
                )
            return deleted
        except asyncpg.ForeignKeyViolationError as e:
            logger.error(
                f"Cannot delete category ID {category_id} for user {user_id} because dependent news sources exist: {e}"
            )
            return False
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error deleting category {category_id} for user {user_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting category {category_id} for user {user_id}: {e}"
            )
            return False
