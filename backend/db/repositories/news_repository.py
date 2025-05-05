#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Repository Module
Provides data access operations for news articles using aiosqlite
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
import asyncpg  # Add asyncpg
from datetime import datetime, timezone  # Import for TIMESTAMPTZ

from db.schema_constants import (
    NEWS_TABLE,
    NEWS_ID,
    NEWS_TITLE,
    NEWS_URL,
    NEWS_SOURCE_NAME,
    NEWS_CATEGORY_NAME,
    NEWS_SOURCE_ID,
    NEWS_CATEGORY_ID,
    NEWS_SUMMARY,
    NEWS_ANALYSIS,
    NEWS_DATE,
    NEWS_CONTENT,
    # NEWS_USER_ID, # Conceptually adding user_id
)

# Note: Assuming 'user_id' column exists conceptually in NEWS_TABLE
NEWS_USER_ID = "user_id"

from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    async def add(self, item: Dict[str, Any], user_id: int) -> Optional[int]:
        """Adds a single news item for a user using ON CONFLICT. Returns new ID or None if exists/failed."""
        url = item.get("url")
        if not item.get("title") or not url:
            logger.warning(
                f"Skipping news item for user {user_id} due to missing title or url: {url}"
            )
            return None

        category_name = item.get("category_name", "Uncategorized")

        # Use INSERT ... ON CONFLICT (url, user_id) DO NOTHING RETURNING id
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}, {NEWS_USER_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT ({NEWS_URL}, {NEWS_USER_ID}) DO NOTHING
            RETURNING {NEWS_ID}
        """
        params = (
            item.get("title"),
            url,
            item.get("source_name"),
            category_name,
            item.get("source_id"),
            item.get("category_id"),
            item.get("summary"),
            item.get("analysis"),
            item.get("date"),
            item.get("content"),
            user_id,  # Add user_id
        )

        try:
            record = await self._fetchone(query_str, params)
            last_id = record[0] if record else None

            if last_id is not None:
                logger.info(
                    f"Added news item '{item.get('title')}' with ID {last_id} for user {user_id}."
                )
            else:
                logger.debug(
                    f"News item with URL {url} for user {user_id} already exists or failed to insert, ON CONFLICT triggered."
                )
            return last_id
        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error adding news item for user {user_id} due to integrity constraint (URL: {url}, FKs: {item.get('source_id')}, {item.get('category_id')}): {e}"
            )
            return None
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news item for user {user_id} (URL: {url}): {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error adding news item for user {user_id} (URL: {url}): {e}"
            )
            return None

    async def add_batch(
        self, items: List[Dict[str, Any]], user_id: int
    ) -> Tuple[int, int]:
        """Adds multiple news items for a user in a batch. Returns (success_count, skipped_count). Uses ON CONFLICT."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        # Fetch URLs only for the current user
        urls_in_db_list = await self.get_all_urls(user_id)
        urls_in_db_set = set(urls_in_db_list)

        processed_urls_in_batch = set()

        for item in items:
            url = item.get("url")
            if not item.get("title") or not url:
                logger.warning(
                    f"Skipping news item for user {user_id} due to missing title or url: {url}"
                )
                skipped_count += 1
                continue

            # Check if URL already exists for this user in DB or was already processed in this batch
            if url in urls_in_db_set or url in processed_urls_in_batch:
                logger.debug(
                    f"Skipping duplicate URL for user {user_id} in batch or DB: {url}"
                )
                skipped_count += 1
                continue

            params = (
                item.get("title", ""),
                url,
                item.get("source_name", ""),
                item.get("category_name", "Uncategorized"),
                item.get("source_id"),
                item.get("category_id"),
                item.get("summary", ""),
                item.get("analysis", ""),
                item.get("date"),
                item.get("content", ""),
                user_id,  # Add user_id
            )
            params_list.append(params)
            processed_urls_in_batch.add(url)

        if not params_list:
            logger.info(
                f"No valid new items found in the batch for user {user_id} to add."
            )
            return 0, skipped_count

        # Use ON CONFLICT (url, user_id) DO NOTHING
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}, {NEWS_USER_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT ({NEWS_URL}, {NEWS_USER_ID}) DO NOTHING
        """

        success_count = 0
        try:
            if await self._executemany(query_str, params_list):
                success_count = len(params_list)
                logger.info(
                    f"Batch add news attempted for {success_count} items for user {user_id}. "
                    f"{skipped_count} items were skipped beforehand (missing data or duplicates)."
                    f" DB handled potential conflicts via ON CONFLICT."
                )

        except asyncpg.IntegrityConstraintViolationError as e:
            logger.error(
                f"Error during batch add news for user {user_id} (check foreign keys): {e}"
            )
            success_count = 0
        except asyncpg.PostgresError as e:
            logger.error(f"Error in batch add news for user {user_id}: {e}")
            success_count = 0
        except Exception as e:
            logger.error(f"Unexpected error in batch add news for user {user_id}: {e}")
            success_count = 0

        return success_count, skipped_count

    async def get_by_id(self, news_id: int, user_id: int) -> Optional[asyncpg.Record]:
        """Gets a news item by its ID for a specific user."""
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}, {NEWS_USER_ID}
            FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1 AND {NEWS_USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (news_id, user_id))
        except Exception as e:
            logger.error(f"Error getting news by ID {news_id} for user {user_id}: {e}")
            return None

    async def get_content_by_id(self, news_id: int, user_id: int) -> Optional[str]:
        """Gets the content of a news item by its ID for a specific user."""
        query_str = f"SELECT {NEWS_CONTENT} FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1 AND {NEWS_USER_ID} = $2"
        try:
            record = await self._fetchone(query_str, (news_id, user_id))
            return record[0] if record else None
        except Exception as e:
            logger.error(
                f"Error getting news content by ID {news_id} for user {user_id}: {e}"
            )
            return None

    async def get_all(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> List[asyncpg.Record]:
        """Gets all news items for a specific user with pagination."""
        query_str = f"""
             SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                    {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                    {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}, {NEWS_USER_ID}
             FROM {NEWS_TABLE}
             WHERE {NEWS_USER_ID} = $1
             ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT $2 OFFSET $3
         """
        try:
            return await self._fetchall(query_str, (user_id, limit, offset))
        except Exception as e:
            logger.error(f"Error getting all news for user {user_id}: {e}")
            return []

    async def get_news_with_filters(
        self,
        user_id: int,  # Add user_id
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[asyncpg.Record]:
        """Gets news items for a specific user with various filters applied."""

        query_base = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}, {NEWS_USER_ID}
            FROM {NEWS_TABLE}
        """
        conditions = [f"{NEWS_USER_ID} = $1"]  # Start with user_id condition
        params = [user_id]
        param_index = 2  # Start next param index at 2

        if category_id is not None:
            conditions.append(f"{NEWS_CATEGORY_ID} = ${param_index}")
            params.append(category_id)
            param_index += 1

        if source_id is not None:
            conditions.append(f"{NEWS_SOURCE_ID} = ${param_index}")
            params.append(source_id)
            param_index += 1

        if analyzed is not None:
            if analyzed:
                conditions.append(
                    f"({NEWS_ANALYSIS} IS NOT NULL AND {NEWS_ANALYSIS} != '')"
                )
            else:
                conditions.append(f"({NEWS_ANALYSIS} IS NULL OR {NEWS_ANALYSIS} = '')")

        if search_term:
            conditions.append(
                f"({NEWS_TITLE} ILIKE ${param_index} OR {NEWS_SUMMARY} ILIKE ${param_index} OR {NEWS_CONTENT} ILIKE ${param_index})"
            )
            params.append(f"%{search_term}%")
            param_index += 1

        where_clause = "WHERE " + " AND ".join(conditions)

        offset = (page - 1) * page_size
        query_suffix = f"ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ${param_index} OFFSET ${param_index + 1}"
        params.extend([page_size, offset])

        query_str = f"{query_base} {where_clause} {query_suffix}"

        try:
            return await self._fetchall(query_str, tuple(params))
        except Exception as e:
            logger.error(f"Error getting filtered news for user {user_id}: {e}")
            return []

    async def delete(self, news_id: int, user_id: int) -> bool:
        """Deletes a news item by ID for a specific user."""
        query_str = (
            f"DELETE FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1 AND {NEWS_USER_ID} = $2"
        )
        try:
            status = await self._execute(query_str, (news_id, user_id))
            deleted = status and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted news item ID {news_id} for user {user_id}.")
            else:
                logger.warning(
                    f"Delete command for news ID {news_id} (User: {user_id}) executed but status was '{status}'. Item might not exist or belong to user."
                )
            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting news item {news_id} for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting news item {news_id} for user {user_id}: {e}"
            )
            return False

    async def exists_by_url(self, url: str, user_id: int) -> bool:
        """Checks if a news item exists with the given URL for a specific user."""
        query_str = f"SELECT 1 FROM {NEWS_TABLE} WHERE {NEWS_URL} = $1 AND {NEWS_USER_ID} = $2 LIMIT 1"
        try:
            record = await self._fetchone(query_str, (url, user_id))
            return record is not None
        except Exception as e:
            logger.error(
                f"Error checking news existence by URL for user {user_id}: {e}"
            )
            return False

    async def get_all_urls(self, user_id: int) -> List[str]:
        """Gets all news URLs for a specific user."""
        query_str = f"SELECT {NEWS_URL} FROM {NEWS_TABLE} WHERE {NEWS_USER_ID} = $1"
        try:
            records = await self._fetchall(query_str, (user_id,))
            # Assuming NEWS_URL is the first column (index 0) if selecting only one column
            return [record[0] for record in records]
        except Exception as e:
            logger.error(f"Error getting all news URLs for user {user_id}: {e}")
            return []

    async def clear_all_for_user(self, user_id: int) -> bool:
        """Deletes all news items for a specific user. Use with caution!"""
        query_str = f"DELETE FROM {NEWS_TABLE} WHERE {NEWS_USER_ID} = $1"
        try:
            status = await self._execute(query_str, (user_id,))
            # Status might report DELETE 0 or DELETE N
            logger.warning(f"Cleared news items for user {user_id}. Status: {status}")
            return True  # Success if no exception
        except asyncpg.PostgresError as e:
            logger.error(f"Error clearing news items for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error clearing news items for user {user_id}: {e}"
            )
            return False

    async def update_analysis(
        self, news_id: int, user_id: int, analysis_text: str
    ) -> bool:
        """Updates the analysis text for a specific news item belonging to a user."""
        query_str = f"UPDATE {NEWS_TABLE} SET {NEWS_ANALYSIS} = $1 WHERE {NEWS_ID} = $2 AND {NEWS_USER_ID} = $3"
        try:
            status = await self._execute(query_str, (analysis_text, news_id, user_id))
            updated = status and status.startswith("UPDATE 1")
            if updated:
                logger.info(
                    f"Updated analysis for news item ID {news_id} for user {user_id}."
                )
            else:
                logger.warning(
                    f"Update analysis command for news ID {news_id} (User: {user_id}) executed but status was '{status}'. Item might not exist or belong to user."
                )
            return updated
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating news analysis for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error updating news analysis for user {user_id}: {e}"
            )
            return False

    # Remove _as_dict methods, base methods return Records

    async def get_news_with_filters_as_dict(
        self,
        user_id: int,  # Add user_id
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Gets news items for a user with filters, returning a list of dictionaries. Excludes content."""
        query_base = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_USER_ID}
            FROM {NEWS_TABLE}
        """
        conditions = [f"{NEWS_USER_ID} = $1"]  # Start with user_id condition
        params = [user_id]
        param_index = 2  # Start next param index at 2

        if category_id is not None:
            conditions.append(f"{NEWS_CATEGORY_ID} = ${param_index}")
            params.append(category_id)
            param_index += 1
        if source_id is not None:
            conditions.append(f"{NEWS_SOURCE_ID} = ${param_index}")
            params.append(source_id)
            param_index += 1
        if analyzed is not None:
            if analyzed:
                conditions.append(
                    f"({NEWS_ANALYSIS} IS NOT NULL AND {NEWS_ANALYSIS} != '')"
                )
            else:
                conditions.append(f"({NEWS_ANALYSIS} IS NULL OR {NEWS_ANALYSIS} = '')")
        if search_term:
            conditions.append(
                f"({NEWS_TITLE} ILIKE ${param_index} OR {NEWS_SUMMARY} ILIKE ${param_index} OR {NEWS_CONTENT} ILIKE ${param_index})"
            )
            params.append(f"%{search_term}%")
            param_index += 1

        where_clause = "WHERE " + " AND ".join(conditions)

        offset = (page - 1) * page_size
        query_suffix = f"ORDER BY {NEWS_DATE} DESC NULLS LAST, {NEWS_ID} DESC LIMIT ${param_index} OFFSET ${param_index + 1}"
        params.extend([page_size, offset])

        query_str = f"{query_base} {where_clause} {query_suffix}"

        try:
            records = await self._fetchall(query_str, tuple(params))
            return [dict(record) for record in records]
        except Exception as e:
            logger.error(
                f"Error getting news with filters as dict for user {user_id}: {e}"
            )
            return []

    async def get_analysis_by_id(self, news_id: int, user_id: int) -> Optional[str]:
        """Gets the analysis of a news item by its ID for a specific user."""
        query_str = f"""
            SELECT {NEWS_ANALYSIS} FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1 AND {NEWS_USER_ID} = $2
        """
        try:
            row = await self._fetchone(query_str, (news_id, user_id))
            return row[0] if row else None
        except Exception as e:
            logger.error(
                f"Error getting news analysis by ID {news_id} for user {user_id}: {e}"
            )
            return None
