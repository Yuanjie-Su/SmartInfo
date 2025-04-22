#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Category Repository Module
"""

import logging
from typing import List, Optional, Tuple

from src.db.schema_constants import NEWS_CATEGORY_TABLE, NEWS_SOURCES_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query_str = f"INSERT OR IGNORE INTO {NEWS_CATEGORY_TABLE} (name) VALUES (?)"
        query = self._execute(query_str, (name,), commit=True)

        if query:
            # Check if insert happened or row existed
            if self._get_rows_affected(query) > 0:
                last_id = self._get_last_insert_id(query)
                if last_id is not None:
                    logger.info(f"Added news category '{name}' with ID {last_id}.")
                    return (
                        int(last_id)
                        if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                        else None
                    )
                else:
                    # Insert happened but ID retrieval failed (shouldn't usually happen)
                    logger.warning(f"Category '{name}' added but failed to get ID.")
                    return None  # Indicate potential issue
            else:
                # INSERT IGNORE: Row likely existed, fetch its ID
                logger.debug(f"Category '{name}' likely already exists. Fetching ID.")
                existing = self.get_by_name(name)  # Calls _fetchone
                return existing[0] if existing else None
        return None  # Execution failed

    def get_by_id(self, category_id: int) -> Optional[Tuple[int, str]]:
        """Gets a category by its ID."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"
        return self._fetchone(query_str, (category_id,))

    def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} WHERE name = ?"
        return self._fetchone(query_str, (name,))

    def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query_str = f"SELECT id, name FROM {NEWS_CATEGORY_TABLE} ORDER BY name"
        return self._fetchall(query_str)
    
    def update(self, category_id: int, new_name: str) -> bool:
        """Updates a category's name."""
        query_str = f"UPDATE {NEWS_CATEGORY_TABLE} SET name = ? WHERE id = ?"
        query = self._execute(query_str, (new_name, category_id), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.info(f"Updated category ID {category_id} to name '{new_name}'.")
            else:
                logger.warning(
                    f"Failed to update category ID {category_id} (not found or no change)."
                )
            return updated
        return False

    def delete(self, category_id: int) -> bool:
        """Deletes a category (and cascades to news_sources)."""
        query_str = f"DELETE FROM {NEWS_CATEGORY_TABLE} WHERE id = ?"
        query = self._execute(query_str, (category_id,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted category ID {category_id} (cascade may apply).")
            return deleted
        return False

    def delete_all(self) -> bool:
        """Deletes all news categories."""
        logger.warning("Attempting to clear all category data using QtSql.")
        if not self._db.transaction():
            logger.error("Failed to start transaction for delete_all categories.")
            return False

        query_del = self._execute(f"DELETE FROM {NEWS_CATEGORY_TABLE}", commit=False)
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_CATEGORY_TABLE}'",
            commit=False,
        )
        cleared = query_del is not None and query_seq is not None

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for delete_all categories: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {NEWS_CATEGORY_TABLE} table.")
        else:
            logger.error(f"Failed to clear categories. Rolling back.")
            self._db.rollback()
        return cleared

    def get_with_source_count(self) -> List[Tuple[int, str, int]]:
        """Gets all categories with the count of associated news sources."""
        query_str = f"""
             SELECT nc.id, nc.name, COUNT(ns.id)
             FROM {NEWS_CATEGORY_TABLE} nc
             LEFT JOIN {NEWS_SOURCES_TABLE} ns ON nc.id = ns.category_id
             GROUP BY nc.id, nc.name
             ORDER BY nc.name
         """
        return self._fetchall(query_str)
