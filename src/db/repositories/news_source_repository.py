# src/db/repositories/news_source_repository.py
# -*- coding: utf-8 -*-

import logging
from typing import List, Optional, Tuple

from src.db.schema_constants import NEWS_SOURCES_TABLE, NEWS_CATEGORY_TABLE
from .base_repository import BaseRepository  # Uses the new QtSql BaseRepository

logger = logging.getLogger(__name__)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations using QSqlQuery."""

    def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new news source. Returns the new ID or existing ID if ignored."""
        # Use INSERT OR IGNORE (SQLite specific)
        query_str = f"INSERT OR IGNORE INTO {NEWS_SOURCES_TABLE} (name, url, category_id) VALUES (?, ?, ?)"
        query = self._execute(query_str, (name, url, category_id), commit=True)

        if query:
            # Check if insert happened (row affected) or row was ignored
            if self._get_rows_affected(query) > 0:
                last_id = self._get_last_insert_id(query)
                if last_id is not None:
                    logger.info(
                        f"Added news source '{name}' ({url}) under category ID {category_id}. ID: {last_id}"
                    )
                    return (
                        int(last_id)
                        if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                        else None
                    )
                else:
                    logger.warning(f"Source '{name}' added but failed to get ID.")
                    return None
            else:
                # INSERT IGNORE: Row likely existed, fetch its ID
                logger.debug(
                    f"Source with URL '{url}' likely already exists. Fetching ID."
                )
                existing = self.get_by_url(url)  # Assumes get_by_url works
                return existing[0] if existing else None  # Return existing ID
        return None  # Execution failed

    def get_by_id(self, source_id: int) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its ID."""
        query_str = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE id = ?"
        )
        return self._fetchone(query_str, (source_id,))

    def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query_str = (
            f"SELECT id, name, url, category_id FROM {NEWS_SOURCES_TABLE} WHERE url = ?"
        )
        return self._fetchone(query_str, (url,))

    def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query_str)

    def get_by_category(self, category_id: int) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources for a specific category ID."""
        query_str = f"""
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM {NEWS_SOURCES_TABLE} ns
            JOIN {NEWS_CATEGORY_TABLE} nc ON ns.category_id = nc.id
            WHERE ns.category_id = ?
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query_str, (category_id,))

    def update(self, source_id: int, name: str, url: str, category_id: int) -> bool:
        """Updates an existing news source."""
        query_str = f"UPDATE {NEWS_SOURCES_TABLE} SET name = ?, url = ?, category_id = ? WHERE id = ?"
        query = self._execute(
            query_str, (name, url, category_id, source_id), commit=True
        )
        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.info(f"Updated news source ID {source_id}.")
            else:
                logger.warning(
                    f"Failed to update news source ID {source_id} (not found or no change)."
                )
            return updated
        return False  # Execution failed

    def delete(self, source_id: int) -> bool:
        """Deletes a news source."""
        query_str = f"DELETE FROM {NEWS_SOURCES_TABLE} WHERE id = ?"
        query = self._execute(query_str, (source_id,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted news source ID {source_id}.")
            else:
                logger.warning(
                    f"Failed to delete news source ID {source_id} (not found?)."
                )
            return deleted
        return False  # Execution failed

    def delete_all(self) -> bool:
        """Deletes all news sources."""
        logger.warning("Attempting to clear all news sources using QtSql.")
        # Manual transaction management
        if not self._db.transaction():
            logger.error("Failed to start transaction for delete_all news sources.")
            return False

        query_del = self._execute(f"DELETE FROM {NEWS_SOURCES_TABLE}", commit=False)
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name=?",
            (NEWS_SOURCES_TABLE,),
            commit=False,
        )

        cleared = query_del is not None and query_seq is not None

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for delete_all news sources: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {NEWS_SOURCES_TABLE} table.")
        else:
            logger.error(
                f"Failed to clear news sources from {NEWS_SOURCES_TABLE}. Rolling back."
            )
            self._db.rollback()

        return cleared
