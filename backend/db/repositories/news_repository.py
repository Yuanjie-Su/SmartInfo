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
)

from db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    async def add(self, item: Dict[str, Any]) -> Optional[int]:
        """Adds a single news item using ON CONFLICT. Returns new ID or None if exists/failed."""
        url = item.get("url")
        if not item.get("title") or not url:
            logger.warning(f"Skipping news item due to missing title or url: {url}")
            return None

        # Removed explicit exists_by_url check; handled by ON CONFLICT

        category_name = item.get("category_name", "Uncategorized")

        # Use INSERT ... ON CONFLICT (url) DO NOTHING RETURNING id
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT ({NEWS_URL}) DO NOTHING
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
            item.get("date"),  # 直接使用date值，不进行转换
            item.get("content"),
        )

        try:
            # Use _fetchone for RETURNING id
            record = await self._fetchone(query_str, params)
            last_id = record[0] if record else None

            if last_id is not None:
                logger.info(f"Added news item '{item.get('title')}' with ID {last_id}.")
            else:
                # This now means the URL already existed and ON CONFLICT was triggered
                logger.debug(
                    f"News item with URL {url} already exists or failed to insert, ON CONFLICT triggered."
                )
            return last_id
        except asyncpg.IntegrityConstraintViolationError as e:
            # Catch other integrity errors like foreign key violations
            logger.error(
                f"Error adding news item due to integrity constraint (URL: {url}, FKs: {item.get('source_id')}, {item.get('category_id')}): {e}"
            )
            return None
        except asyncpg.PostgresError as e:
            logger.error(f"Error adding news item (URL: {url}): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding news item (URL: {url}): {e}")
            return None

    async def add_batch(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Adds multiple news items in a batch. Returns (success_count, skipped_count). Uses ON CONFLICT."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        # Fetch all URLs and convert to a set for efficient lookup (O(1) average)
        urls_in_db_list = await self.get_all_urls()
        urls_in_db_set = set(urls_in_db_list)

        processed_urls_in_batch = set()  # Keep track of URLs processed in this batch

        for item in items:
            url = item.get("url")
            if not item.get("title") or not url:
                logger.warning(f"Skipping news item due to missing title or url: {url}")
                skipped_count += 1
                continue

            # Check if URL already exists in DB or was already processed in this batch
            if url in urls_in_db_set or url in processed_urls_in_batch:
                logger.debug(f"Skipping duplicate URL in batch or DB: {url}")
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
                item.get("date"),  # Directly use the date value
                item.get("content", ""),
            )
            params_list.append(params)
            processed_urls_in_batch.add(url)  # Mark URL as processed for this batch

        if not params_list:
            logger.info("No valid new items found in the batch to add.")
            return 0, skipped_count

        # Change placeholders to $n, use ON CONFLICT DO NOTHING
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT ({NEWS_URL}) DO NOTHING
        """

        success_count = 0
        try:
            # Use _executemany
            # Success means the command executed without raising a DB error
            # Note: _executemany doesn't return the number of affected rows directly in asyncpg
            # like execute does. We assume success if no error is raised.
            # The ON CONFLICT clause handles duplicates gracefully in the DB.
            if await self._executemany(query_str, params_list):
                success_count = len(
                    params_list
                )  # Count items attempted in the batch insert
                logger.info(
                    f"Batch add news attempted for {success_count} items. "
                    f"{skipped_count} items were skipped beforehand (missing data or duplicates)."
                    f" DB handled potential conflicts via ON CONFLICT."
                )

        except asyncpg.IntegrityConstraintViolationError as e:
            # This might catch FK violations if IDs are invalid
            logger.error(f"Error during batch add news (check foreign keys): {e}")
            # Cannot reliably determine partial success without more complex logic
            success_count = 0
        except asyncpg.PostgresError as e:
            logger.error(f"Error in batch add news: {e}")
            success_count = 0
        except Exception as e:
            logger.error(f"Unexpected error in batch add news: {e}")
            success_count = 0

        # The success_count here represents items successfully passed to executemany,
        # not necessarily rows inserted (due to ON CONFLICT).
        # The skipped_count represents items filtered out *before* the DB call.
        return success_count, skipped_count

    # Update return type hint (Dict -> asyncpg.Record)
    async def get_by_id(self, news_id: int) -> Optional[asyncpg.Record]:
        """Gets a news item by its ID."""
        # Change placeholder to $1
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1
        """
        try:
            # _fetchone returns Record or None
            # Remove _row_to_dict call
            return await self._fetchone(query_str, (news_id,))
        except Exception as e:
            logger.error(f"Error getting news by ID: {e}")
            return None  # Or re-raise

    async def get_content_by_id(self, news_id: int) -> Optional[str]:
        """Gets the content of a news item by its ID."""
        query_str = f"SELECT {NEWS_CONTENT} FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1"
        try:
            # Use _fetchone and access the first element
            record = await self._fetchone(query_str, (news_id,))
            return record[0] if record else None
        except Exception as e:
            logger.error(f"Error getting news content by ID: {e}")
            return None  # Or re-raise

    # Update return type hint (List[Dict] -> List[asyncpg.Record])
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[asyncpg.Record]:
        """Gets all news items with pagination."""
        # Change placeholders to $1, $2
        query_str = f"""
             SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                    {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                    {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
             FROM {NEWS_TABLE} ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT $1 OFFSET $2
         """
        try:
            # _fetchall returns List[Record]
            # Remove list comprehension with _row_to_dict
            return await self._fetchall(query_str, (limit, offset))
        except Exception as e:
            logger.error(f"Error getting all news: {e}")
            return []  # Or re-raise

    # Update return type hint (List[Dict] -> List[asyncpg.Record])
    async def get_news_with_filters(
        self,
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[asyncpg.Record]:
        """Gets news items with various filters applied.

        The 'analyzed' parameter checks for the presence of content in the analysis field,
        not a separate 'analyzed' column which doesn't exist in the DB schema.
        """

        # Start with base query
        query_base = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            FROM {NEWS_TABLE}
        """
        conditions = []
        params = []
        param_index = 1

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
                # Check if analysis is not NULL and not empty string
                conditions.append(
                    f"({NEWS_ANALYSIS} IS NOT NULL AND {NEWS_ANALYSIS} != '')"
                )
            else:
                # Check if analysis IS NULL or empty string
                conditions.append(f"({NEWS_ANALYSIS} IS NULL OR {NEWS_ANALYSIS} = '')")
            # No parameter needed for IS NULL/IS NOT NULL checks

        if search_term:
            # Use ILIKE for case-insensitive search in PostgreSQL
            conditions.append(
                f"({NEWS_TITLE} ILIKE ${param_index} OR {NEWS_SUMMARY} ILIKE ${param_index} OR {NEWS_CONTENT} ILIKE ${param_index})"
            )
            params.append(f"%{search_term}%")
            param_index += 1

        # Build WHERE clause
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Add ordering, limit, offset
        offset = (page - 1) * page_size
        query_suffix = f"ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ${param_index} OFFSET ${param_index + 1}"
        params.extend([page_size, offset])

        query_str = f"{query_base} {where_clause} {query_suffix}"

        try:
            # _fetchall returns List[Record]
            # Remove list comprehension with _row_to_dict
            return await self._fetchall(query_str, tuple(params))
        except Exception as e:
            logger.error(f"Error getting filtered news: {e}")
            return []  # Or re-raise

    async def delete(self, news_id: int) -> bool:
        """Deletes a news item by ID."""
        query_str = f"DELETE FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1"
        try:
            # Use _execute
            status = await self._execute(query_str, (news_id,))
            deleted = status and status.startswith("DELETE 1")
            if deleted:
                logger.info(f"Deleted news item ID {news_id}.")
            else:
                logger.warning(
                    f"Delete command for news ID {news_id} executed but status was '{status}'."
                )

            return deleted
        except asyncpg.PostgresError as e:
            logger.error(f"Error deleting news item: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting news item: {e}")
            return False

    async def exists_by_url(self, url: str) -> bool:
        """Checks if a news item exists with the given URL."""
        # Change placeholder to $1
        query_str = f"SELECT 1 FROM {NEWS_TABLE} WHERE {NEWS_URL} = $1 LIMIT 1"
        try:
            # Use _fetchone
            record = await self._fetchone(query_str, (url,))
            return record is not None
        except Exception as e:
            logger.error(f"Error checking news existence by URL: {e}")
            return False  # Or re-raise

    async def get_all_urls(self) -> List[str]:
        """Gets all news URLs."""
        query_str = f"SELECT {NEWS_URL} FROM {NEWS_TABLE}"
        try:
            records = await self._fetchall(query_str)
            return [record[NEWS_URL.lower()] for record in records]
        except Exception as e:
            logger.error(f"Error getting all news URLs: {e}")
            return []

    async def clear_all(self) -> bool:
        """Deletes all news items. Use with caution!"""
        # Use TRUNCATE for efficiency, or DELETE if TRUNCATE permissions are an issue
        # query_str = f"TRUNCATE TABLE {NEWS_TABLE}" # Faster, but requires TRUNCATE privilege
        query_str = f"DELETE FROM {NEWS_TABLE}"  # Slower, uses DELETE privilege

        try:
            # Use _execute
            status = await self._execute(query_str)
            logger.warning(f"Cleared all news items. Status: {status}")
            return True  # Success if no exception
        except asyncpg.PostgresError as e:
            logger.error(f"Error clearing all news items: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error clearing all news items: {e}")
            return False

    async def update_analysis(self, news_id: int, analysis_text: str) -> bool:
        """Updates the analysis text for a specific news item."""
        # Change placeholders to $1, $2
        query_str = f"UPDATE {NEWS_TABLE} SET {NEWS_ANALYSIS} = $1 WHERE {NEWS_ID} = $2"
        try:
            # Use _execute
            status = await self._execute(query_str, (analysis_text, news_id))
            updated = status and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated analysis for news item ID {news_id}.")
            else:
                logger.warning(
                    f"Update analysis command for news ID {news_id} executed but status was '{status}'."
                )
            return updated
        except asyncpg.PostgresError as e:
            logger.error(f"Error updating news analysis: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating news analysis: {e}")
            return False

    # Remove _as_dict methods, base methods return Records
    # async def get_by_id_as_dict(self, news_id: int) -> Optional[asyncpg.Record]: ...
    # async def get_all_as_dict(...) -> List[asyncpg.Record]: ...

    # Keep this method if explicit dict conversion is needed for API response structure
    # but modify it to work with asyncpg.Record input from get_news_with_filters
    async def get_news_with_filters_as_dict(
        self,
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[Dict[str, Any]]:  # Return List[Dict] as intended by original method name
        """Gets news items with filters, returning a list of dictionaries.

        Excludes content field from the results.
        """
        # Reuse the logic from get_news_with_filters but select fewer columns
        query_base = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}
            FROM {NEWS_TABLE}
        """
        conditions = []
        params = []
        param_index = 1

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

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        offset = (page - 1) * page_size
        query_suffix = f"ORDER BY {NEWS_DATE} DESC NULLS LAST, {NEWS_ID} DESC LIMIT ${param_index} OFFSET ${param_index + 1}"  # Added NULLS LAST
        params.extend([page_size, offset])

        query_str = f"{query_base} {where_clause} {query_suffix}"

        try:
            # Use _fetchall to get List[Record]
            records = await self._fetchall(query_str, tuple(params))
            # Convert list of Records to list of Dicts
            return [dict(record) for record in records]
        except Exception as e:
            logger.error(f"Error getting news with filters as dict: {e}")
            return []

    async def get_analysis_by_id(self, news_id: int) -> Optional[str]:
        """Gets the analysis of a news item by its ID."""
        query_str = f"""
            SELECT {NEWS_ANALYSIS} FROM {NEWS_TABLE} WHERE {NEWS_ID} = $1
        """
        try:
            row = await self._fetchone(query_str, (news_id,))
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting news analysis by ID: {e}")
            return None
