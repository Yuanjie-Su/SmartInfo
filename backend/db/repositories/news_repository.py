#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Repository Module (Async)
Provides data access operations for news articles
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    async def add(self, item: Dict[str, Any]) -> Optional[int]:
        """Adds a single news item. Returns new ID or None if failed/exists."""
        # Basic validation
        if not item.get("title") or not item.get("link"):
            logger.warning(
                f"Skipping news item due to missing title or link: {item.get('link')}"
            )
            return None

        # Check for duplicates by link
        if await self.exists_by_link(item["link"]):
            logger.debug(f"News with link {item['link']} already exists, skipping.")
            return None

        # Prepare data
        query = """
            INSERT INTO news (
                title, link, source_name, category_name, source_id, category_id,
                summary, analysis, date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            item.get("title"),
            item.get("link"),
            item.get("source_name"),
            item.get("category_name"),
            item.get("source_id"),
            item.get("category_id"),
            item.get("summary"),
            item.get("analysis"),
            item.get("date"),
        )

        cursor = await self._execute(query, params, commit=True)
        if cursor and cursor.lastrowid:
            logger.info(
                f"Added news item '{item.get('title')}' with ID {cursor.lastrowid}."
            )
            return cursor.lastrowid
        return None

    async def add_batch(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Adds multiple news items in a batch. Returns (success_count, skipped_count)."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        processed_links = set(await self.get_all_links())  # Get existing links efficiently

        for item in items:
            link = item.get("link")
            if not item.get("title") or not link:
                skipped_count += 1
                continue
            if link in processed_links:
                skipped_count += 1
                continue

            params = (
                item.get("title"),
                link,
                item.get("source_name"),
                item.get("category_name"),
                item.get("source_id"),
                item.get("category_id"),
                item.get("summary"),
                item.get("analysis"),
                item.get("date"),
            )
            params_list.append(params)
            processed_links.add(link)  # Add to set to avoid duplicates within the batch

        if not params_list:
            return 0, skipped_count

        query = """
            INSERT INTO news (
                title, link, source_name, category_name, source_id, category_id,
                summary, analysis, date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        success_count = await self._executemany(query, params_list, commit=True)

        # Adjust skipped count if execute_many reported fewer inserts than expected (unlikely with IGNORE but possible)
        if success_count != len(params_list):
            logger.warning(
                f"Expected to insert {len(params_list)} items, but DB reported {success_count}. Transaction might have partially failed or links existed."
            )

        logger.info(f"Batch add news: {success_count} added, {skipped_count} skipped.")
        return success_count, skipped_count

    async def get_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Gets a news item by its ID."""
        query = """
            SELECT id, title, link, source_name, category_name, source_id, category_id,
                   summary, analysis, date
            FROM news WHERE id = ?
        """
        row = await self._fetchone(query, (news_id,))
        return self._row_to_dict(row) if row else None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Gets all news items with pagination."""
        query = """
             SELECT id, title, link, source_name, category_name, source_id, category_id,
                    summary, analysis, date
             FROM news ORDER BY date DESC, id DESC LIMIT ? OFFSET ?
         """
        rows = await self._fetchall(query, (limit, offset))
        return [self._row_to_dict(row) for row in rows]

    async def delete(self, news_id: int) -> bool:
        """Deletes a news item."""
        query = "DELETE FROM news WHERE id = ?"
        cursor = await self._execute(query, (news_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news item ID {news_id}.")
        return deleted

    async def exists_by_link(self, link: str) -> bool:
        """Checks if a news item exists by its link."""
        query = "SELECT 1 FROM news WHERE link = ? LIMIT 1"
        return await self._fetchone(query, (link,)) is not None

    async def get_all_links(self) -> List[str]:
        """Gets all unique links currently in the news table."""
        query = "SELECT link FROM news"
        rows = await self._fetchall(query)
        return [row[0] for row in rows]

    async def clear_all(self) -> bool:
        """Deletes all news items from the table."""
        logger.warning("Attempting to clear all news data.")
        # Reset auto-increment separately if needed after delete
        cursor_seq = await self._execute(
            "DELETE FROM sqlite_sequence WHERE name='news'", commit=False
        )  # Commit handled by next query
        cursor_del = await self._execute("DELETE FROM news", commit=True)
        cleared = cursor_del is not None
        if cleared:
            logger.info("Cleared all data from news table.")
        return cleared

    def _row_to_dict(self, row: Tuple) -> Optional[Dict[str, Any]]:
        """Converts a database row tuple to a dictionary."""
        if not row:
            return None
        # Match the order of columns in the SELECT statement
        return {
            "id": row[0],
            "title": row[1],
            "link": row[2],
            "source_name": row[3],
            "category_name": row[4],
            "source_id": row[5],
            "category_id": row[6],
            "summary": row[7],
            "analysis": row[8],
            "date": row[9],
        }
