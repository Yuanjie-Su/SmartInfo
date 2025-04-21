#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Repository Module
Provides data access operations for news articles
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from src.db.schema_constants import NEWS_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    def add(self, item: Dict[str, Any]) -> Optional[int]:
        """Adds a single news item. Returns new ID or None if failed/exists."""
        # Basic validation
        if not item.get("title") or not item.get("url"):
            logger.warning(
                f"Skipping news item due to missing title or url: {item.get('url')}"
            )
            return None

        # Check for duplicates by url
        if self.exists_by_url(item["url"]):
            logger.debug(f"News with url {item['url']} already exists, skipping.")
            return None

        # Prepare query and params
        query_str = f"""
            INSERT INTO {NEWS_TABLE} (
                title, url, source_name, category_name, source_id, category_id,
                summary, analysis, date, content
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

        # Execute using the new base method, commit=True
        query = self._execute(
            query_str, params, commit=True
        )  # _execute now returns QSqlQuery

        if query:
            last_id = self._get_last_insert_id(query)
            if last_id is not None:
                logger.info(f"Added news item '{item.get('title')}' with ID {last_id}.")
                # Ensure the ID type is appropriate (likely int)
                return (
                    int(last_id)
                    if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                    else None
                )
            else:
                # This might happen if the table doesn't have AUTOINCREMENT or similar
                logger.warning(
                    f"News item '{item.get('title')}' added but could not retrieve lastInsertId."
                )
                return None  # Or indicate success differently?
        return None  # _execute failed

    def add_batch(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Adds multiple news items in a batch. Returns (success_count, skipped_count)."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        processed_urls = set(self.get_all_urls())  # Get existing urls efficiently

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
                title, url, source_name, category_name, source_id, category_id,
                summary, analysis, date, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # Use the new _executemany
        success_count = self._executemany(query_str, params_list, commit=True)

        # The returned success_count from _executemany is now the number of successful inserts
        final_skipped = len(items) - success_count  # More accurate skipped count

        logger.info(f"Batch add news: {success_count} added, {final_skipped} skipped.")
        return success_count, final_skipped

    def get_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Gets a news item by its ID."""
        query_str = f"""
            SELECT id, title, url, source_name, category_name, source_id, category_id,
                   summary, analysis, date, content
            FROM {NEWS_TABLE} WHERE id = ?
        """
        row = self._fetchone(query_str, (news_id,))
        return self._row_to_dict(row) if row else None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Gets all news items with pagination."""
        query_str = f"""
             SELECT id, title, url, source_name, category_name, source_id, category_id,
                    summary, analysis, date, content
             FROM {NEWS_TABLE} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?
         """
        rows = self._fetchall(query_str, (limit, offset))
        return [self._row_to_dict(row) for row in rows]

    def delete(self, news_id: int) -> bool:
        """Deletes a news item."""
        query_str = f"DELETE FROM {NEWS_TABLE} WHERE id = ?"
        query = self._execute(query_str, (news_id,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted news item ID {news_id}.")
            return deleted
        return False

    def exists_by_url(self, url: str) -> bool:
        """Checks if a news item exists by its url."""
        query_str = f"SELECT 1 FROM {NEWS_TABLE} WHERE url = ? LIMIT 1"
        return self._fetchone(query_str, (url,)) is not None

    def get_all_urls(self) -> List[str]:
        """Gets all unique urls currently in the news table."""
        query_str = f"SELECT url FROM {NEWS_TABLE}"
        rows = self._fetchall(query_str)
        return [row[0] for row in rows]

    def clear_all(self) -> bool:
        """Deletes all news items from the table."""
        logger.warning("Attempting to clear all news data.")

        # Start transaction
        if not self._db.transaction():
            logger.error("Failed to start transaction for clear_all.")
            return False

        # First query: delete all data
        query_del = self._execute(f"DELETE FROM {NEWS_TABLE}", commit=False)
        if not query_del:
            logger.error(f"Failed to delete data from {NEWS_TABLE}. Rolling back.")
            self._db.rollback()
            return False

        # Second query: reset autoincrement sequence
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_TABLE}'", commit=False
        )
        if not query_seq:
            logger.error(f"Failed to reset sequence for {NEWS_TABLE}. Rolling back.")
            self._db.rollback()
            return False

        # Commit transaction
        if not self._db.commit():
            logger.error(
                f"Failed to commit transaction for clear_all: {self._db.lastError().text()}"
            )
            self._db.rollback()
            return False

        logger.info(f"Cleared all data from {NEWS_TABLE} table.")
        return True

    def _row_to_dict(self, row: Tuple) -> Optional[Dict[str, Any]]:
        """Converts a database row tuple to a dictionary."""
        if not row:
            return None
        # Match the order of columns in the SELECT statement
        return {
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
            "content": row[10],
        }

    def update_analysis(self, news_id: int, analysis_text: str) -> bool:
        """
        Updates the analysis field of a news item.

        Args:
            news_id: The ID of the news item to update
            analysis_text: The analysis result text

        Returns:
            True if the update was successful, False otherwise
        """
        query_str = f"UPDATE {NEWS_TABLE} SET analysis = ? WHERE id = ?"
        query = self._execute(query_str, (analysis_text, news_id), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.info(f"Updated analysis content for news ID {news_id}.")
            else:
                logger.warning(f"Failed to update analysis content for news ID {news_id}, ID might not exist.")
            return updated
        return False
