#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Repository Module
Provides data access operations for news articles using aiosqlite
"""

import logging
from typing import List, Dict, Optional, Tuple, Any

from backend.db.schema_constants import (
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

from backend.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    async def add(self, item: Dict[str, Any]) -> Optional[int]:
        """Adds a single news item. Returns new ID or None if failed/exists."""
        # Basic validation
        if not item.get("title") or not item.get("url"):
            logger.warning(
                f"Skipping news item due to missing title or url: {item.get('url')}"
            )
            return None

        # Check for duplicates by url
        if await self.exists_by_url(item["url"]):
            logger.debug(f"News with url {item['url']} already exists, skipping.")
            return None

        # Ensure category_name has a default value if missing
        if not item.get("category_name"):
            item["category_name"] = "Uncategorized"

        # Prepare query and params
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            item.get("title"),
            item.get("url"),
            item.get("source_name"),
            item.get("category_name"),
            item.get("source_id"),
            item.get("category_id"),
            item.get("summary"),
            item.get("analysis"),
            item.get("date"),
            item.get("content"),
        )

        try:
            cursor = await self._execute(query_str, params, commit=True)
            last_id = self._get_last_insert_id(cursor)
            if last_id:
                logger.info(f"Added news item '{item.get('title')}' with ID {last_id}.")
            return last_id
        except Exception as e:
            logger.error(f"Error adding news item: {e}")
            return None

    async def add_batch(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Adds multiple news items in a batch. Returns (success_count, skipped_count)."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        processed_urls = set(await self.get_all_urls())  # Get existing urls efficiently

        for item in items:
            url = item.get("url")
            if not item.get("title") or not url:
                skipped_count += 1
                continue
            if url in processed_urls:
                skipped_count += 1
                continue

            params = (
                item.get("title", ""),
                url,
                item.get("source_name", ""),
                item.get("category_name", ""),
                item.get("source_id"),
                item.get("category_id"),
                item.get("summary", ""),
                item.get("analysis", ""),
                item.get("date", ""),
                item.get("content", ""),
            )
            params_list.append(params)
            processed_urls.add(url)  # Add to set to avoid duplicates within the batch

        if not params_list:
            return 0, skipped_count

        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME}, {NEWS_CATEGORY_NAME},
                {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID}, {NEWS_SUMMARY},
                {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        success_count = 0
        try:
            success_count = await self._executemany(query_str, params_list, commit=True)
            logger.info(
                f"Batch add news: {success_count} added, {skipped_count} skipped."
            )
        except Exception as e:
            logger.error(f"Error in batch add news: {e}")

        return success_count, skipped_count

    async def get_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Gets a news item by its ID."""
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            FROM {NEWS_TABLE} WHERE {NEWS_ID} = ?
        """
        try:
            row = await self._fetchone(query_str, (news_id,))
            return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting news by ID: {e}")
            return None

    async def get_content_by_id(self, news_id: int) -> Optional[str]:
        """Gets the content of a news item by its ID."""
        query_str = f"""
            SELECT {NEWS_CONTENT} FROM {NEWS_TABLE} WHERE {NEWS_ID} = ?
        """
        try:
            row = await self._fetchone(query_str, (news_id,))
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting news content by ID: {e}")
            return None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Gets all news items with pagination."""
        query_str = f"""
             SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                    {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                    {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
             FROM {NEWS_TABLE} ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ? OFFSET ?
         """
        try:
            rows = await self._fetchall(query_str, (limit, offset))
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all news: {e}")
            return []

    async def get_news_with_filters(
        self,
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Gets news items with various filters applied.

        The 'analyzed' parameter checks for the presence of content in the analysis field,
        not a separate 'analyzed' column which doesn't exist in the DB schema.
        """

        # Start with base query
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            FROM {NEWS_TABLE}
            WHERE 1=1
        """

        # Build parameters list
        params = []

        # Add filters
        if category_id is not None:
            query_str += f" AND {NEWS_CATEGORY_ID} = ?"
            params.append(category_id)

        if source_id is not None:
            query_str += f" AND {NEWS_SOURCE_ID} = ?"
            params.append(source_id)

        if analyzed is not None:
            if analyzed:
                query_str += (
                    f" AND {NEWS_ANALYSIS} IS NOT NULL AND {NEWS_ANALYSIS} != ''"
                )
            else:
                query_str += f" AND ({NEWS_ANALYSIS} IS NULL OR {NEWS_ANALYSIS} = '')"

        if search_term:
            # Add search condition for title and content
            query_str += f" AND ({NEWS_TITLE} LIKE ? OR {NEWS_CONTENT} LIKE ?)"
            search_param = f"%{search_term}%"
            params.append(search_param)
            params.append(search_param)

        # Add pagination and ordering
        query_str += f" ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        params.append(page_size)
        params.append(offset)

        try:
            rows = await self._fetchall(query_str, tuple(params))
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting news with filters: {e}")
            return []

    async def delete(self, news_id: int) -> bool:
        """Deletes a news item by ID."""
        query_str = f"DELETE FROM {NEWS_TABLE} WHERE {NEWS_ID} = ?"
        try:
            cursor = await self._execute(query_str, (news_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0
            if deleted:
                logger.info(f"Deleted news ID {news_id}.")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting news: {e}")
            return False

    async def exists_by_url(self, url: str) -> bool:
        """Checks if a news item exists with the given URL."""
        query_str = f"SELECT 1 FROM {NEWS_TABLE} WHERE {NEWS_URL} = ? LIMIT 1"
        try:
            row = await self._fetchone(query_str, (url,))
            return row is not None
        except Exception as e:
            logger.error(f"Error checking if news exists by URL: {e}")
            return False

    async def get_all_urls(self) -> List[str]:
        """Gets all URLs from the news table."""
        query_str = f"SELECT {NEWS_URL} FROM {NEWS_TABLE}"
        try:
            rows = await self._fetchall(query_str)
            return [row[0] for row in rows if row and row[0]]
        except Exception as e:
            logger.error(f"Error getting all news URLs: {e}")
            return []

    async def clear_all(self) -> bool:
        """Clears all news items from the table."""
        query_str = f"DELETE FROM {NEWS_TABLE}"
        try:
            await self._execute(query_str, commit=True)
            logger.info("Cleared all news items.")
            return True
        except Exception as e:
            logger.error(f"Error clearing all news: {e}")
            return False

    def _row_to_dict(self, row: Tuple) -> Optional[Dict[str, Any]]:
        """Converts a row tuple to a dictionary."""
        if not row:
            return None
        return {
            NEWS_ID: row[0],
            NEWS_TITLE: row[1],
            NEWS_URL: row[2],
            NEWS_SOURCE_NAME: row[3],
            NEWS_CATEGORY_NAME: row[4],
            NEWS_SOURCE_ID: row[5],
            NEWS_CATEGORY_ID: row[6],
            NEWS_SUMMARY: row[7],
            NEWS_ANALYSIS: row[8],
            NEWS_DATE: row[9],
            NEWS_CONTENT: row[10],
        }

    async def update_analysis(self, news_id: int, analysis_text: str) -> bool:
        """Updates the analysis field for a news item."""
        query_str = f"UPDATE {NEWS_TABLE} SET {NEWS_ANALYSIS} = ? WHERE {NEWS_ID} = ?"
        try:
            cursor = await self._execute(
                query_str, (analysis_text, news_id), commit=True
            )
            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated analysis for news ID {news_id}.")
            return updated
        except Exception as e:
            logger.error(f"Error updating news analysis: {e}")
            return False

    async def get_by_id_as_dict(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Gets a news item by its ID as a dictionary."""
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
            FROM {NEWS_TABLE} WHERE {NEWS_ID} = ?
        """
        try:
            return await self._fetchone_as_dict(query_str, (news_id,))
        except Exception as e:
            logger.error(f"Error getting news by ID as dict: {e}")
            return None

    async def get_all_as_dict(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Gets all news items with pagination as dictionaries."""
        query_str = f"""
             SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                    {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                    {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}, {NEWS_CONTENT}
             FROM {NEWS_TABLE} ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ? OFFSET ?
         """
        try:
            return await self._fetch_as_dict(query_str, (limit, offset))
        except Exception as e:
            logger.error(f"Error getting all news as dict: {e}")
            return []

    async def get_news_with_filters_as_dict(
        self,
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        analyzed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Gets news items with various filters applied and returns as dicts.

        Excludes content field from the results to optimize data transfer.
        The 'analyzed' parameter checks for the presence of content in the analysis field.
        """

        # Start with base query
        query_str = f"""
            SELECT {NEWS_ID}, {NEWS_TITLE}, {NEWS_URL}, {NEWS_SOURCE_NAME},
                   {NEWS_CATEGORY_NAME}, {NEWS_SOURCE_ID}, {NEWS_CATEGORY_ID},
                   {NEWS_SUMMARY}, {NEWS_ANALYSIS}, {NEWS_DATE}
            FROM {NEWS_TABLE}
            WHERE 1=1
        """

        # Build parameters list
        params = []

        # Add filters
        if category_id is not None:
            query_str += f" AND {NEWS_CATEGORY_ID} = ?"
            params.append(category_id)

        if source_id is not None:
            query_str += f" AND {NEWS_SOURCE_ID} = ?"
            params.append(source_id)

        if analyzed is not None:
            if analyzed:
                query_str += (
                    f" AND {NEWS_ANALYSIS} IS NOT NULL AND {NEWS_ANALYSIS} != ''"
                )
            else:
                query_str += f" AND ({NEWS_ANALYSIS} IS NULL OR {NEWS_ANALYSIS} = '')"

        if search_term:
            # Add search condition for title and content
            query_str += f" AND ({NEWS_TITLE} LIKE ? OR {NEWS_CONTENT} LIKE ?)"
            search_param = f"%{search_term}%"
            params.append(search_param)
            params.append(search_param)

        # Add pagination and ordering
        query_str += f" ORDER BY {NEWS_DATE} DESC, {NEWS_ID} DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        params.append(page_size)
        params.append(offset)

        try:
            rows = await self._fetchall(query_str, tuple(params))
            # Convert rows to dictionaries with column names
            results = []
            for row in rows:
                news_dict = {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "source_name": row[3],
                    "category_name": row[4],
                    "source_id": row[5],
                    "category_id": row[6],
                    "summary": row[7],
                    "analysis": row[8],
                    "date": row[9],
                }
                results.append(news_dict)
            return results
        except Exception as e:
            logger.error(f"Error getting news with filters as dict: {e}")
            return []

    async def get_analysis_by_id(self, news_id: int) -> Optional[str]:
        """Gets the analysis of a news item by its ID."""
        query_str = f"""
            SELECT {NEWS_ANALYSIS} FROM {NEWS_TABLE} WHERE {NEWS_ID} = ?
        """
        try:
            row = await self._fetchone(query_str, (news_id,))
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting news analysis by ID: {e}")
            return None
