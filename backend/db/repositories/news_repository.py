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

from db.schema_constants import News

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
            INSERT INTO {News.TABLE_NAME} (
                {News.TITLE}, {News.URL}, {News.SOURCE_NAME}, {News.CATEGORY_NAME},
                {News.SOURCE_ID}, {News.CATEGORY_ID}, {News.SUMMARY},
                {News.ANALYSIS}, {News.DATE}, {News.CONTENT}, {News.USER_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT ({News.URL}, {News.USER_ID}) DO NOTHING
            RETURNING {News.ID}
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
                user_id,
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
            INSERT INTO {News.TABLE_NAME} (
                {News.TITLE}, {News.URL}, {News.SOURCE_NAME}, {News.CATEGORY_NAME},
                {News.SOURCE_ID}, {News.CATEGORY_ID}, {News.SUMMARY},
                {News.ANALYSIS}, {News.DATE}, {News.CONTENT}, {News.USER_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT ({News.URL}, {News.USER_ID}) DO NOTHING
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
            SELECT {News.ID}, {News.TITLE}, {News.URL}, {News.SOURCE_NAME},
                   {News.CATEGORY_NAME}, {News.SOURCE_ID}, {News.CATEGORY_ID},
                   {News.SUMMARY}, {News.ANALYSIS}, {News.DATE}, {News.CONTENT}, {News.USER_ID}
            FROM {News.TABLE_NAME} WHERE {News.ID} = $1 AND {News.USER_ID} = $2
        """
        try:
            return await self._fetchone(query_str, (news_id, user_id))
        except Exception as e:
            logger.error(f"Error getting news by ID {news_id} for user {user_id}: {e}")
            return None

    async def get_content_by_id(self, news_id: int, user_id: int) -> Optional[str]:
        """Gets only the content field of a news item by its ID for a specific user."""
        query_str = f"""
            SELECT {News.CONTENT}
            FROM {News.TABLE_NAME} WHERE {News.ID} = $1 AND {News.USER_ID} = $2
        """
        try:
            record = await self._fetchone(query_str, (news_id, user_id))
            return record["content"] if record else None
        except Exception as e:
            logger.error(f"Error getting news content by ID {news_id}: {e}")
            return None

    async def get_all(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> List[asyncpg.Record]:
        """Gets all news items for a user, with limit and offset."""
        query_str = f"""
            SELECT {News.ID}, {News.TITLE}, {News.URL}, {News.SOURCE_NAME},
                   {News.CATEGORY_NAME}, {News.SOURCE_ID}, {News.CATEGORY_ID},
                   {News.SUMMARY}, {News.ANALYSIS}, {News.DATE}, {News.USER_ID}
            FROM {News.TABLE_NAME} WHERE {News.USER_ID} = $1
            ORDER BY {News.ID} DESC LIMIT $2 OFFSET $3
        """
        try:
            return await self._fetchall(query_str, (user_id, limit, offset))
        except Exception as e:
            logger.error(f"Error getting all news: {e}")
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
        """Gets news items with various filters applied, paginated."""
        # Start with base query
        base_query = f"""
            SELECT
                {News.ID}, {News.TITLE}, {News.URL}, {News.SOURCE_NAME},
                {News.CATEGORY_NAME}, {News.SOURCE_ID}, {News.CATEGORY_ID},
                {News.SUMMARY}, {News.ANALYSIS}, {News.DATE}, {News.USER_ID}
            FROM {News.TABLE_NAME}
            WHERE {News.USER_ID} = $1
        """

        # Parameters list, starting with user_id
        params = [user_id]
        param_index = 2  # Next parameter index (PostgreSQL uses $1, $2, etc.)

        # Add filter conditions
        conditions = []
        if category_id is not None:
            conditions.append(f"{News.CATEGORY_ID} = ${param_index}")
            params.append(category_id)
            param_index += 1

        if source_id is not None:
            conditions.append(f"{News.SOURCE_ID} = ${param_index}")
            params.append(source_id)
            param_index += 1

        if analyzed is not None:
            if analyzed:
                conditions.append(
                    f"{News.ANALYSIS} IS NOT NULL AND {News.ANALYSIS} != ''"
                )
            else:
                conditions.append(f"({News.ANALYSIS} IS NULL OR {News.ANALYSIS} = '')")

        if search_term:
            search_param = f"%{search_term}%"
            conditions.append(
                f"({News.TITLE} ILIKE ${param_index} OR {News.CONTENT} ILIKE ${param_index})"
            )
            params.append(search_param)
            param_index += 1

        # Combine conditions
        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        # Add pagination
        offset = (page - 1) * page_size
        base_query += (
            f" ORDER BY {News.ID} DESC LIMIT ${param_index} OFFSET ${param_index + 1}"
        )
        params.extend([page_size, offset])

        try:
            return await self._fetchall(base_query, tuple(params))
        except Exception as e:
            logger.error(f"Error in get_news_with_filters: {e}")
            return []

    async def delete(self, news_id: int, user_id: int) -> bool:
        """Deletes a news item by its ID for a specific user."""
        query_str = f"""
            DELETE FROM {News.TABLE_NAME}
            WHERE {News.ID} = $1 AND {News.USER_ID} = $2
        """
        try:
            result = await self._execute(query_str, (news_id, user_id))
            if result and result.lower() == "delete 1":
                logger.info(f"Deleted news item with ID {news_id} for user {user_id}")
                return True
            else:
                logger.warning(
                    f"No news item found with ID {news_id} for user {user_id} for deletion"
                )
                return False
        except Exception as e:
            logger.error(f"Error deleting news by ID {news_id}: {e}")
            return False

    async def exists_by_url(self, url: str, user_id: int) -> bool:
        """Checks if a news item with the given URL exists for the user."""
        query_str = f"""
            SELECT 1 FROM {News.TABLE_NAME}
            WHERE {News.URL} = $1 AND {News.USER_ID} = $2
            LIMIT 1
        """
        try:
            return bool(await self._fetchone(query_str, (url, user_id)))
        except Exception as e:
            logger.error(f"Error checking if news URL exists: {e}")
            return False

    async def get_all_urls(self, user_id: int) -> List[str]:
        """Gets all URLs for a specific user."""
        query_str = f"""
            SELECT {News.URL} FROM {News.TABLE_NAME}
            WHERE {News.USER_ID} = $1
        """
        try:
            records = await self._fetchall(query_str, (user_id,))
            return [record["url"] for record in records]
        except Exception as e:
            logger.error(f"Error getting all news URLs: {e}")
            return []

    async def clear_all_for_user(self, user_id: int) -> bool:
        """Clears all news items for a user."""
        query_str = f"""
            DELETE FROM {News.TABLE_NAME} WHERE {News.USER_ID} = $1
        """
        try:
            result = await self._execute(query_str, (user_id,))
            if result:
                logger.info(f"Cleared all news for user {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error clearing all news for user {user_id}: {e}")
            return False

    async def update_analysis(
        self, news_id: int, user_id: int, analysis_text: str
    ) -> bool:
        """Updates the analysis field for a news item."""
        # Track the updated timestamp implicitly to avoid extra queries
        query_str = f"""
            UPDATE {News.TABLE_NAME}
            SET {News.ANALYSIS} = $1
            WHERE {News.ID} = $2 AND {News.USER_ID} = $3
        """
        try:
            result = await self._execute(query_str, (analysis_text, news_id, user_id))
            if result and result.lower() == "update 1":
                logger.info(
                    f"Updated analysis for news ID {news_id} for user {user_id}"
                )
                return True
            else:
                logger.warning(
                    f"No news found with ID {news_id} for user {user_id} for analysis update"
                )
                return False
        except Exception as e:
            logger.error(f"Error updating analysis for news ID {news_id}: {e}")
            return False

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
        """Gets news items with various filters applied, paginated, returning dictionaries."""
        result_records = await self.get_news_with_filters(
            user_id=user_id,
            category_id=category_id,
            source_id=source_id,
            analyzed=analyzed,
            page=page,
            page_size=page_size,
            search_term=search_term,
        )

        # Convert to list of dictionaries
        result_dicts = []
        for record in result_records:
            item_dict = dict(record)
            # Clean up None values for better JSON serialization
            for key, value in item_dict.items():
                if value is None:
                    item_dict[key] = ""
            result_dicts.append(item_dict)

        return result_dicts

    async def get_analysis_by_id(self, news_id: int, user_id: int) -> Optional[str]:
        """Gets only the analysis field of a news item by its ID for a specific user."""
        query_str = f"""
            SELECT {News.ANALYSIS}
            FROM {News.TABLE_NAME} WHERE {News.ID} = $1 AND {News.USER_ID} = $2
        """
        try:
            record = await self._fetchone(query_str, (news_id, user_id))
            return record["analysis"] if record else None
        except Exception as e:
            logger.error(f"Error getting news analysis by ID {news_id}: {e}")
            return None
