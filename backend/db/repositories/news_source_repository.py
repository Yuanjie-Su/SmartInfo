#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Source Repository Module for FastAPI backend
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg

from db.schema_constants import (
    NEWS_SOURCES_TABLE,
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCE_ID,
    NEWS_SOURCE_NAME,
    NEWS_SOURCE_URL,
    NEWS_SOURCE_CATEGORY_ID,
    NEWS_CATEGORY_ID,
    NEWS_CATEGORY_NAME,
)
from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    async def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new source. Returns the new ID or existing ID if conflict."""
        query_insert = f"""
            INSERT INTO {NEWS_SOURCES_TABLE} ({NEWS_SOURCE_NAME}, {NEWS_SOURCE_URL}, {NEWS_SOURCE_CATEGORY_ID}) VALUES ($1, $2, $3)
            ON CONFLICT ({NEWS_SOURCE_URL}) DO NOTHING
            RETURNING {NEWS_SOURCE_ID}
        """
        query_select = f"SELECT {NEWS_SOURCE_ID} FROM {NEWS_SOURCES_TABLE} WHERE {NEWS_SOURCE_URL} = $1"
        params = (name, url, category_id)

        try:
            # Use _fetchone for RETURNING id
            record = await self._fetchone(query_insert, params)
            inserted_id = record[0] if record else None

            if inserted_id is not None:
                logger.info(f"Added news source '{name}' with ID {inserted_id}.")
                return inserted_id
            else:
                logger.debug(
                    f"Source with URL {url} likely already exists. Fetching ID."
                )
                # Use _fetchone for SELECT id
                existing_record = await self._fetchone(query_select, (url,))
                existing_id = existing_record[0] if existing_record else None
                if existing_id is not None:
                    logger.debug(
                        f"Found existing source '{name}' with URL {url} and ID {existing_id}."
                    )
                    return existing_id
                else:
                    logger.error(
                        f"Source URL {url} conflict occurred but failed to fetch existing ID."
                    )
                    return None

        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error adding news source '{name}' (check category_id {category_id}): {e}"
            )
            return None
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news source: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding news source: {e}")
            return None

    async def update(
        self, source_id: int, name: str, url: str, category_id: int
    ) -> bool:
        """Updates an existing source."""
        query_str = f"""
            UPDATE {NEWS_SOURCES_TABLE}
            SET {NEWS_SOURCE_NAME} = $1, {NEWS_SOURCE_URL} = $2, {NEWS_SOURCE_CATEGORY_ID} = $3
            WHERE {NEWS_SOURCE_ID} = $4
        """
        params = (name, url, category_id, source_id)

        try:
            status = await self._execute(query_str, params)
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated source ID {source_id}.")
            else:
                logger.warning(
                    f"Update command for source ID {source_id} executed but status was '{status}'."
                )
            return updated
        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error updating source ID {source_id} (check URL '{url}' uniqueness and category_id {category_id}): {e}"
            )
            return False
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating news source: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating news source: {e}")
            return False

    async def delete(self, source_id: int) -> bool:
        """Deletes a source."""
        query_str = f"DELETE FROM {NEWS_SOURCES_TABLE} WHERE {NEWS_SOURCE_ID} = $1"

        try:
            status = await self._execute(query_str, (source_id,))
            deleted = status is not None and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted source ID {source_id}.")
            else:
                logger.warning(
                    f"Delete command for source ID {source_id} executed but status was '{status}'."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting news source {source_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting news source: {e}")
            return False

    async def get_by_id(self, source_id: int) -> Optional[asyncpg.Record]:
        """Gets a source by its ID."""
        query_str = f"""
            SELECT {NEWS_SOURCE_ID}, {NEWS_SOURCE_NAME}, {NEWS_SOURCE_URL}, {NEWS_SOURCE_CATEGORY_ID} 
            FROM {NEWS_SOURCES_TABLE} 
            WHERE {NEWS_SOURCE_ID} = $1
        """

        try:
            return await self._fetchone(query_str, (source_id,))
        except Exception as e:
            logger.error(f"Error getting news source by ID: {e}")
            return None

    async def get_by_url(self, url: str) -> Optional[asyncpg.Record]:
        """Gets a source by its URL."""
        query_str = f"""
            SELECT {NEWS_SOURCE_ID}, {NEWS_SOURCE_NAME}, {NEWS_SOURCE_URL}, {NEWS_SOURCE_CATEGORY_ID} 
            FROM {NEWS_SOURCES_TABLE} 
            WHERE {NEWS_SOURCE_URL} = $1
        """

        try:
            return await self._fetchone(query_str, (url,))
        except Exception as e:
            logger.error(f"Error getting news source by URL: {e}")
            return None

    async def get_all(self) -> List[asyncpg.Record]:
        """Gets all sources with category names."""
        query_str = f"""
            SELECT ns.{NEWS_SOURCE_ID}, ns.{NEWS_SOURCE_NAME}, ns.{NEWS_SOURCE_URL}, ns.{NEWS_SOURCE_CATEGORY_ID}, 
                   nc.{NEWS_CATEGORY_NAME} as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.{NEWS_SOURCE_CATEGORY_ID} = nc.{NEWS_CATEGORY_ID}
            ORDER BY nc.{NEWS_CATEGORY_NAME}, ns.{NEWS_SOURCE_NAME}
        """

        try:
            return await self._fetchall(query_str)
        except Exception as e:
            logger.error(f"Error getting all news sources: {e}")
            return []

    async def get_by_category(self, category_id: int) -> List[asyncpg.Record]:
        """Gets all sources for a specific category ID."""
        query_str = f"""
            SELECT ns.{NEWS_SOURCE_ID}, ns.{NEWS_SOURCE_NAME}, ns.{NEWS_SOURCE_URL}, ns.{NEWS_SOURCE_CATEGORY_ID}, 
                   nc.{NEWS_CATEGORY_NAME} as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.{NEWS_SOURCE_CATEGORY_ID} = nc.{NEWS_CATEGORY_ID}
            WHERE ns.{NEWS_SOURCE_CATEGORY_ID} = $1
            ORDER BY nc.{NEWS_CATEGORY_NAME}, ns.{NEWS_SOURCE_NAME}
        """

        try:
            return await self._fetchall(query_str, (category_id,))
        except Exception as e:
            logger.error(f"Error getting news sources by category: {e}")
            return []

    async def exists_by_url(self, url: str) -> bool:
        """Checks if a source exists with the given URL."""
        query_str = (
            f"SELECT 1 FROM {NEWS_SOURCES_TABLE} WHERE {NEWS_SOURCE_URL} = $1 LIMIT 1"
        )

        try:
            # Use _fetchone and check if a record was returned
            record = await self._fetchone(query_str, (url,))
            return record is not None
        except Exception as e:
            logger.error(f"Error checking if news source exists by URL: {e}")
            return False

    async def exists_by_name(self, name: str) -> bool:
        """Checks if a source exists with the given name."""
        query_str = (
            f"SELECT 1 FROM {NEWS_SOURCES_TABLE} WHERE {NEWS_SOURCE_NAME} = $1 LIMIT 1"
        )

        try:
            # Use _fetchone and check if a record was returned
            record = await self._fetchone(query_str, (name,))
            return record is not None
        except Exception as e:
            logger.error(f"Error checking if news source exists by name: {e}")
            return False
