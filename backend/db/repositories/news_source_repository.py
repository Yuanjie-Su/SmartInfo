#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

from db.schema_constants import NewsSource
from db.schema_constants import NewsCategory

# Note: Assuming 'user_id' column exists conceptually in NEWS_SOURCES_TABLE
NEWS_SOURCE_USER_ID = "user_id"

from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    async def add(
        self, name: str, url: str, category_id: int, user_id: int
    ) -> Optional[int]:
        """Adds a new source for a user. Returns the new ID or existing ID if conflict."""
        query_insert = f"""
            INSERT INTO {NewsSource.TABLE_NAME} ({NewsSource.NAME}, {NewsSource.URL}, {NewsSource.CATEGORY_ID}, {NewsSource.USER_ID})
            VALUES ($1, $2, $3, $4)
            ON CONFLICT ({NewsSource.URL}, {NewsSource.USER_ID}) DO NOTHING
            RETURNING {NewsSource.ID}
        """
        query_select = f"SELECT {NewsSource.ID} FROM {NewsSource.TABLE_NAME} WHERE {NewsSource.URL} = $1 AND {NewsSource.USER_ID} = $2"
        params_insert = (name, url, category_id, user_id)
        params_select = (url, user_id)

        try:
            record = await self._fetchone(query_insert, params_insert)
            inserted_id = record[0] if record else None

            if inserted_id is not None:
                logger.info(
                    f"Added news source '{name}' with ID {inserted_id} for user {user_id}."
                )
                return inserted_id
            else:
                logger.debug(
                    f"Source with URL {url} for user {user_id} likely already exists. Fetching ID."
                )
                existing_record = await self._fetchone(query_select, params_select)
                existing_id = existing_record[0] if existing_record else None
                if existing_id is not None:
                    logger.debug(
                        f"Found existing source '{name}' with URL {url} and ID {existing_id} for user {user_id}."
                    )
                    return existing_id
                else:
                    logger.error(
                        f"Source URL {url} conflict for user {user_id} occurred but failed to fetch existing ID."
                    )
                    return None

        except asyncpg.IntegrityConstraintViolationError as e:
            # This could be the ON CONFLICT or a FK violation on category_id
            # If it's the ON CONFLICT, the logic above handles it. If FK, log error.
            if "violates foreign key constraint" in str(e).lower():
                logger.error(
                    f"Error adding news source '{name}' for user {user_id} (check category_id {category_id}): {e}"
                )
            # else: assume it was the ON CONFLICT handled above
            return None
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news source for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding news source for user {user_id}: {e}")
            return None

    async def update(
        self, source_id: int, user_id: int, name: str, url: str, category_id: int
    ) -> bool:
        """Updates an existing source belonging to a user."""
        query_str = f"""
            UPDATE {NewsSource.TABLE_NAME}
            SET {NewsSource.NAME} = $1, {NewsSource.URL} = $2, {NewsSource.CATEGORY_ID} = $3
            WHERE {NewsSource.ID} = $4 AND {NewsSource.USER_ID} = $5
        """
        params = (name, url, category_id, source_id, user_id)

        try:
            status = await self._execute(query_str, params)
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated source ID {source_id} for user {user_id}.")
            else:
                logger.warning(
                    f"Update command for source ID {source_id} (User: {user_id}) executed but status was '{status}'. Source might not exist or belong to user."
                )
            return updated
        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error updating source ID {source_id} for user {user_id} (check URL '{url}' uniqueness for user and category_id {category_id}): {e}"
            )
            return False
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating news source for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error updating news source for user {user_id}: {e}"
            )
            return False

    async def delete(self, source_id: int, user_id: int) -> bool:
        """Deletes a source belonging to a user."""
        query_str = f"DELETE FROM {NewsSource.TABLE_NAME} WHERE {NewsSource.ID} = $1 AND {NewsSource.USER_ID} = $2"

        try:
            status = await self._execute(query_str, (source_id, user_id))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted source ID {source_id} for user {user_id}.")
            else:
                logger.warning(
                    f"Delete command for source ID {source_id} (User: {user_id}) executed but status was '{status}'. Source might not exist or belong to user."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error deleting news source {source_id} for user {user_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting news source {source_id} for user {user_id}: {e}"
            )
            return False

    async def get_by_id(self, source_id: int, user_id: int) -> Optional[asyncpg.Record]:
        """Gets a source by its ID for a specific user."""
        query_str = f"""
            SELECT {NewsSource.ID}, {NewsSource.NAME}, {NewsSource.URL}, {NewsSource.CATEGORY_ID}, {NewsSource.USER_ID}
            FROM {NewsSource.TABLE_NAME}
            WHERE {NewsSource.ID} = $1 AND {NewsSource.USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (source_id, user_id))
        except Exception as e:
            logger.error(
                f"Error getting news source by ID {source_id} for user {user_id}: {e}"
            )
            return None

    async def get_by_name(self, name: str, user_id: int) -> Optional[asyncpg.Record]:
        """Gets a source by its name for a specific user."""
        query_str = f"""
            SELECT {NewsSource.ID}, {NewsSource.NAME}, {NewsSource.URL}, {NewsSource.CATEGORY_ID}, {NewsSource.USER_ID}
            FROM {NewsSource.TABLE_NAME}
            WHERE {NewsSource.NAME} = $1 AND {NewsSource.USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (name, user_id))
        except Exception as e:
            logger.error(
                f"Error getting news source by name '{name}' for user {user_id}: {e}"
            )
            return None

    async def get_by_url(self, url: str, user_id: int) -> Optional[asyncpg.Record]:
        """Gets a source by its URL for a specific user."""
        query_str = f"""
            SELECT {NewsSource.ID}, {NewsSource.NAME}, {NewsSource.URL}, {NewsSource.CATEGORY_ID}, {NewsSource.USER_ID}
            FROM {NewsSource.TABLE_NAME}
            WHERE {NewsSource.URL} = $1 AND {NewsSource.USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (url, user_id))
        except Exception as e:
            logger.error(
                f"Error getting news source by URL '{url}' for user {user_id}: {e}"
            )
            return None

    async def get_all(self, user_id: int) -> List[asyncpg.Record]:
        """Gets all sources for a specific user with category names."""
        query_str = f"""
            SELECT ns.{NewsSource.ID}, ns.{NewsSource.NAME}, ns.{NewsSource.URL}, ns.{NewsSource.CATEGORY_ID}, ns.{NewsSource.USER_ID},
                   nc.{NewsCategory.NAME} as category_name
            FROM {NewsSource.TABLE_NAME} ns
            JOIN {NewsCategory.TABLE_NAME} nc ON ns.{NewsSource.CATEGORY_ID} = nc.{NewsCategory.ID}
            WHERE ns.{NewsSource.USER_ID} = $1 AND nc.{NewsCategory.USER_ID} = $1 -- Ensure category also belongs to user
            ORDER BY nc.{NewsCategory.NAME}, ns.{NewsSource.NAME}
        """
        try:
            return await self._fetchall(query_str, (user_id,))
        except Exception as e:
            logger.error(f"Error getting all news sources for user {user_id}: {e}")
            return []

    async def get_by_category(
        self, category_id: int, user_id: int
    ) -> List[asyncpg.Record]:
        """Gets all sources for a specific category ID belonging to a user."""
        query_str = f"""
            SELECT ns.{NewsSource.ID}, ns.{NewsSource.NAME}, ns.{NewsSource.URL}, ns.{NewsSource.CATEGORY_ID}, ns.{NewsSource.USER_ID},
                   nc.{NewsCategory.NAME} as category_name
            FROM {NewsSource.TABLE_NAME} ns
            JOIN {NewsCategory.TABLE_NAME} nc ON ns.{NewsSource.CATEGORY_ID} = nc.{NewsCategory.ID}
            WHERE ns.{NewsSource.CATEGORY_ID} = $1 AND ns.{NewsSource.USER_ID} = $2 AND nc.{NewsCategory.USER_ID} = $2 -- Ensure both source and category belong to user
            ORDER BY nc.{NewsCategory.NAME}, ns.{NewsSource.NAME}
        """
        try:
            return await self._fetchall(query_str, (category_id, user_id))
        except Exception as e:
            logger.error(
                f"Error getting news sources by category {category_id} for user {user_id}: {e}"
            )
            return []

    async def exists_by_url(self, url: str, user_id: int) -> bool:
        """Checks if a source exists with the given URL for a specific user."""
        query_str = f"SELECT 1 FROM {NewsSource.TABLE_NAME} WHERE {NewsSource.URL} = $1 AND {NewsSource.USER_ID} = $2 LIMIT 1"
        try:
            record = await self._fetchone(query_str, (url, user_id))
            return record is not None
        except Exception as e:
            logger.error(
                f"Error checking if news source exists by URL for user {user_id}: {e}"
            )
            return False

    async def exists_by_name(self, name: str, user_id: int) -> bool:
        """Checks if a source exists with the given name for a specific user."""
        query_str = f"SELECT 1 FROM {NewsSource.TABLE_NAME} WHERE {NewsSource.NAME} = $1 AND {NewsSource.USER_ID} = $2 LIMIT 1"
        try:
            record = await self._fetchone(query_str, (name, user_id))
            return record is not None
        except Exception as e:
            logger.error(
                f"Error checking if news source exists by name for user {user_id}: {e}"
            )
            return False
