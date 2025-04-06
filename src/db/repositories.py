#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database repository module
Encapsulates specific operations on database tables (CRUD)
"""

import logging
import sqlite3
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

# Get database connection function from .connection
from .connection import get_db

logger = logging.getLogger(__name__)


# --- Base Repository (Optional but helpful) ---
class BaseRepository:
    def __init__(self):
        self._conn = get_db()

    def _execute(
        self, query: str, params: tuple = (), commit: bool = False
    ) -> Optional[sqlite3.Cursor]:
        """Executes a query and returns the cursor."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            if commit:
                self._conn.commit()
            return cursor
        except sqlite3.Error as e:
            logger.error(
                f"DB Error executing query: {query} with params {params}. Error: {e}",
                exc_info=True,
            )
            if commit:
                self._conn.rollback()
            return None

    def _fetchone(self, query: str, params: tuple = ()) -> Optional[Tuple]:
        """Executes a query and fetches one row."""
        cursor = self._execute(query, params)
        return cursor.fetchone() if cursor else None

    def _fetchall(self, query: str, params: tuple = ()) -> List[Tuple]:
        """Executes a query and fetches all rows."""
        cursor = self._execute(query, params)
        return cursor.fetchall() if cursor else []

    def _executemany(
        self, query: str, params_list: List[tuple], commit: bool = True
    ) -> int:
        """Executes a query with multiple parameter sets."""
        try:
            cursor = self._conn.cursor()
            cursor.executemany(query, params_list)
            rowcount = cursor.rowcount
            if commit:
                self._conn.commit()
            return rowcount
        except sqlite3.Error as e:
            logger.error(f"DB Error executing many: {query}. Error: {e}", exc_info=True)
            if commit:
                self._conn.rollback()
            return 0


# --- Specific Repositories ---


class NewsCategoryRepository(BaseRepository):
    """Repository for news_category table operations."""

    def add(self, name: str) -> Optional[int]:
        """Adds a new category. Returns the new ID or None if failed/exists."""
        query = "INSERT OR IGNORE INTO news_category (name) VALUES (?)"
        cursor = self._execute(query, (name,), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added news category '{name}' with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = self.get_by_name(name)
            return existing[0] if existing else None
        return None

    def get_by_id(self, category_id: int) -> Optional[Tuple[int, str]]:
        """Gets a category by its ID."""
        query = "SELECT id, name FROM news_category WHERE id = ?"
        return self._fetchone(query, (category_id,))

    def get_by_name(self, name: str) -> Optional[Tuple[int, str]]:
        """Gets a category by its name."""
        query = "SELECT id, name FROM news_category WHERE name = ?"
        return self._fetchone(query, (name,))

    def get_all(self) -> List[Tuple[int, str]]:
        """Gets all categories."""
        query = "SELECT id, name FROM news_category ORDER BY name"
        return self._fetchall(query)

    def update(self, category_id: int, new_name: str) -> bool:
        """Updates a category's name."""
        query = "UPDATE news_category SET name = ? WHERE id = ?"
        cursor = self._execute(query, (new_name, category_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated category ID {category_id} to name '{new_name}'.")
        return updated

    def delete(self, category_id: int) -> bool:
        """Deletes a category (and cascades to news_sources)."""
        # Note: CASCADE DELETE is handled by DB schema if defined correctly
        query = "DELETE FROM news_category WHERE id = ?"
        cursor = self._execute(query, (category_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted category ID {category_id} (cascade may apply).")
        return deleted

    def get_with_source_count(self) -> List[Tuple[int, str, int]]:
        """Gets all categories with the count of associated news sources."""
        query = """
             SELECT nc.id, nc.name, COUNT(ns.id)
             FROM news_category nc
             LEFT JOIN news_sources ns ON nc.id = ns.category_id
             GROUP BY nc.id, nc.name
             ORDER BY nc.name
         """
        return self._fetchall(query)


class NewsSourceRepository(BaseRepository):
    """Repository for news_sources table operations."""

    def add(self, name: str, url: str, category_id: int) -> Optional[int]:
        """Adds a new news source."""
        query = "INSERT OR IGNORE INTO news_sources (name, url, category_id) VALUES (?, ?, ?)"
        cursor = self._execute(query, (name, url, category_id), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(
                f"Added news source '{name}' ({url}) under category ID {category_id}."
            )
            return cursor.lastrowid
        elif cursor:  # IGNORE case, row exists
            existing = self.get_by_url(url)
            return existing[0] if existing else None
        return None

    def get_by_id(self, source_id: int) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its ID."""
        query = "SELECT id, name, url, category_id FROM news_sources WHERE id = ?"
        return self._fetchone(query, (source_id,))

    def get_by_url(self, url: str) -> Optional[Tuple[int, str, str, int]]:
        """Gets a source by its URL."""
        query = "SELECT id, name, url, category_id FROM news_sources WHERE url = ?"
        return self._fetchone(query, (url,))

    def get_all(self) -> List[Tuple[int, str, str, int, str]]:
        """Gets all sources with category names."""
        query = """
            SELECT ns.id, ns.name, ns.url, ns.category_id, nc.name as category_name
            FROM news_sources ns
            JOIN news_category nc ON ns.category_id = nc.id
            ORDER BY nc.name, ns.name
        """
        return self._fetchall(query)

    def get_by_category(self, category_id: int) -> List[Tuple[int, str, str]]:
        """Gets all sources for a specific category ID."""
        query = (
            "SELECT id, name, url FROM news_sources WHERE category_id = ? ORDER BY name"
        )
        return self._fetchall(query, (category_id,))

    def update(self, source_id: int, name: str, url: str, category_id: int) -> bool:
        """Updates an existing news source."""
        query = (
            "UPDATE news_sources SET name = ?, url = ?, category_id = ? WHERE id = ?"
        )
        cursor = self._execute(query, (name, url, category_id, source_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated news source ID {source_id}.")
        return updated

    def delete(self, source_id: int) -> bool:
        """Deletes a news source."""
        query = "DELETE FROM news_sources WHERE id = ?"
        cursor = self._execute(query, (source_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news source ID {source_id}.")
        return deleted


class NewsRepository(BaseRepository):
    """Repository for news table operations."""

    def add(self, item: Dict[str, Any]) -> Optional[int]:
        """Adds a single news item. Returns new ID or None if failed/exists."""
        # Basic validation
        if not item.get("title") or not item.get("link"):
            logger.warning(
                f"Skipping news item due to missing title or link: {item.get('link')}"
            )
            return None

        # Check for duplicates by link
        if self.exists_by_link(item["link"]):
            logger.debug(f"News with link {item['link']} already exists, skipping.")
            return None

        # Prepare data
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO news (
                title, link, source_name, category_name, source_id, category_id,
                summary, content, llm_analysis, analyzed, embedded, published_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            item.get("title"),
            item.get("link"),
            item.get("source_name"),
            item.get("category_name"),
            item.get("source_id"),
            item.get("category_id"),
            item.get("summary"),
            item.get("content"),
            item.get("llm_analysis"),
            bool(item.get("llm_analysis")),
            bool(item.get("embedded", False)),
            item.get("published_date"),
        )

        cursor = self._execute(query, params, commit=True)
        if cursor and cursor.lastrowid:
            logger.info(
                f"Added news item '{item.get('title')}' with ID {cursor.lastrowid}."
            )
            return cursor.lastrowid
        return None

    def add_batch(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Adds multiple news items in a batch. Returns (success_count, skipped_count)."""
        if not items:
            return 0, 0

        params_list = []
        skipped_count = 0
        processed_links = set(self.get_all_links())  # Get existing links efficiently
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                item.get("content"),
                item.get("llm_analysis"),
                bool(item.get("llm_analysis")),
                bool(item.get("embedded", False)),
                item.get("published_date"),
            )
            params_list.append(params)
            processed_links.add(link)  # Add to set to avoid duplicates within the batch

        if not params_list:
            return 0, skipped_count

        query = """
            INSERT INTO news (
                title, link, source_name, category_name, source_id, category_id,
                summary, content, llm_analysis, analyzed, embedded, published_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        success_count = self._executemany(query, params_list, commit=True)

        # Adjust skipped count if execute_many reported fewer inserts than expected (unlikely with IGNORE but possible)
        # skipped_count = len(items) - success_count # More accurate way
        if success_count != len(params_list):
            logger.warning(
                f"Expected to insert {len(params_list)} items, but DB reported {success_count}. Transaction might have partially failed or links existed."
            )
            # Re-query might be needed for absolute accuracy, but this gives an indication.
            # For simplicity, we return the calculated skipped_count and reported success_count.

        logger.info(f"Batch add news: {success_count} added, {skipped_count} skipped.")
        return success_count, skipped_count

    def get_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Gets a news item by its ID."""
        query = """
            SELECT id, title, link, source_name, category_name, source_id, category_id,
                   summary, content, llm_analysis, analyzed, embedded, published_date
            FROM news WHERE id = ?
        """
        row = self._fetchone(query, (news_id,))
        return self._row_to_dict(row) if row else None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Gets all news items with pagination."""
        query = """
             SELECT id, title, link, source_name, category_name, source_id, category_id,
                    summary, content, llm_analysis, analyzed, embedded, published_date
             FROM news ORDER BY published_date DESC, id DESC LIMIT ? OFFSET ?
         """
        rows = self._fetchall(query, (limit, offset))
        return [self._row_to_dict(row) for row in rows]

    def get_unanalyzed(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Gets unanalyzed news items."""
        query = """
            SELECT id, title, link, source_name, category_name, source_id, category_id,
                   summary, content, published_date
            FROM news WHERE analyzed = 0 ORDER BY published_date ASC, id ASC LIMIT ?
        """  # Process older items first
        rows = self._fetchall(query, (limit,))
        # Return dicts with needed fields for analysis
        return [
            {
                "id": row[0],
                "title": row[1],
                "link": row[2],
                "source_name": row[3],
                "category_name": row[4],
                "source_id": row[5],
                "category_id": row[6],
                "summary": row[7],
                "content": row[8],
                "published_date": row[9],
            }
            for row in rows
        ]

    def get_unembedded(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Gets news items that haven't been embedded yet."""
        # Fetch items that have content (summary or full content) and are not embedded
        query = """
            SELECT id, title, summary, content
            FROM news
            WHERE embedded = 0 AND (summary IS NOT NULL AND summary != '' OR content IS NOT NULL AND content != '')
            ORDER BY published_date ASC, id ASC
            LIMIT ?
        """
        rows = self._fetchall(query, (limit,))
        return [
            {"id": row[0], "title": row[1], "summary": row[2], "content": row[3]}
            for row in rows
        ]

    def update_analysis(self, news_id: int, analysis_text: str) -> bool:
        """Updates the LLM analysis for a news item and marks it as analyzed."""
        query = "UPDATE news SET llm_analysis = ?, analyzed = 1 WHERE id = ?"
        cursor = self._execute(query, (analysis_text, news_id), commit=True)
        updated = cursor.rowcount > 0 if cursor else False
        if updated:
            logger.info(f"Updated analysis for news ID {news_id}.")
        return updated

    def mark_embedded_batch(self, news_ids: List[int]) -> bool:
        """Marks multiple news items as embedded."""
        if not news_ids:
            return True
        query = "UPDATE news SET embedded = 1 WHERE id IN ({})".format(
            ",".join("?" * len(news_ids))
        )
        cursor = self._execute(query, tuple(news_ids), commit=True)
        updated = cursor.rowcount == len(news_ids) if cursor else False
        if updated:
            logger.info(f"Marked {len(news_ids)} news items as embedded.")
        else:
            logger.warning(
                f"Failed to mark all requested news items as embedded ({len(news_ids)} requested)."
            )
        return updated

    def delete(self, news_id: int) -> bool:
        """Deletes a news item."""
        query = "DELETE FROM news WHERE id = ?"
        cursor = self._execute(query, (news_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted news item ID {news_id}.")
        return deleted

    def exists_by_link(self, link: str) -> bool:
        """Checks if a news item exists by its link."""
        query = "SELECT 1 FROM news WHERE link = ? LIMIT 1"
        return self._fetchone(query, (link,)) is not None

    def get_all_links(self) -> List[str]:
        """Gets all unique links currently in the news table."""
        query = "SELECT link FROM news"
        rows = self._fetchall(query)
        return [row[0] for row in rows]

    def clear_all(self) -> bool:
        """Deletes all news items from the table."""
        logger.warning("Attempting to clear all news data.")
        # Reset auto-increment separately if needed after delete
        cursor_seq = self._execute(
            "DELETE FROM sqlite_sequence WHERE name='news'", commit=False
        )  # Commit handled by next query
        cursor_del = self._execute("DELETE FROM news", commit=True)
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
            "content": row[8],
            "llm_analysis": row[9],
            "analyzed": bool(row[10]),
            "embedded": bool(row[11]),
            "published_date": row[12],
        }


class ApiKeyRepository(BaseRepository):
    """Repository for api_config table operations."""

    def save_key(self, api_name: str, api_key: str) -> bool:
        """Saves or updates an API key."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO api_config (api_name, api_key, created_date, modified_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_name) DO UPDATE SET
                api_key = excluded.api_key,
                modified_date = excluded.modified_date
        """
        cursor = self._execute(query, (api_name, api_key, now, now), commit=True)
        saved = cursor is not None
        if saved:
            logger.info(f"Saved/Updated API key for '{api_name}'.")
        return saved

    def get_key(self, api_name: str) -> Optional[str]:
        """Gets an API key by name."""
        query = "SELECT api_key FROM api_config WHERE api_name = ?"
        result = self._fetchone(query, (api_name,))
        return result[0] if result else None

    def delete_key(self, api_name: str) -> bool:
        """Deletes an API key."""
        query = "DELETE FROM api_config WHERE api_name = ?"
        cursor = self._execute(query, (api_name,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted API key for '{api_name}'.")
        return deleted

    def get_all_keys_info(self) -> List[Tuple[str, str, str]]:
        """Gets info (name, created, modified) for all keys."""
        query = "SELECT api_name, created_date, modified_date FROM api_config"
        return self._fetchall(query)


class SystemConfigRepository(BaseRepository):
    """Repository for system_config table operations."""

    def get_config(self, key: str) -> Optional[str]:
        """Gets a system config value by key."""
        query = "SELECT config_value FROM system_config WHERE config_key = ?"
        result = self._fetchone(query, (key,))
        return result[0] if result else None

    def save_config(
        self, key: str, value: str, description: Optional[str] = None
    ) -> bool:
        """Saves or updates a system config value."""
        query = """
             INSERT INTO system_config (config_key, config_value, description)
             VALUES (?, ?, ?)
             ON CONFLICT(config_key) DO UPDATE SET
                 config_value = excluded.config_value,
                 description = COALESCE(excluded.description, description)
         """
        cursor = self._execute(query, (key, value, description), commit=True)
        saved = cursor is not None
        if saved:
            logger.info(f"Saved/Updated system config key '{key}'.")
        return saved

    def get_all_configs(self) -> Dict[str, str]:
        """Gets all system configurations."""
        query = "SELECT config_key, config_value FROM system_config"
        rows = self._fetchall(query)
        return {row[0]: row[1] for row in rows}

    def delete_config(self, key: str) -> bool:
        """Deletes a system config key."""
        query = "DELETE FROM system_config WHERE config_key = ?"
        cursor = self._execute(query, (key,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted system config key '{key}'.")
        return deleted

    def delete_all(self) -> bool:
        """Deletes all system config keys."""
        logger.warning("Attempting to clear all system configuration.")
        cursor = self._execute("DELETE FROM system_config", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from system_config table.")
        return cleared


class QARepository(BaseRepository):
    """Repository for qa_history table operations."""

    def add_entry(
        self, question: str, answer: str, context_ids: Optional[List[str]] = None
    ) -> Optional[int]:
        """Adds a new Q&A history entry."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_str = ",".join(context_ids) if context_ids else ""
        query = """
             INSERT INTO qa_history (question, answer, context_ids, created_date)
             VALUES (?, ?, ?, ?)
         """
        cursor = self._execute(query, (question, answer, context_str, now), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added QA history entry with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        return None

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Gets the most recent Q&A history entries."""
        query = """
             SELECT id, question, answer, context_ids, created_date
             FROM qa_history
             ORDER BY created_date DESC
             LIMIT ?
         """
        rows = self._fetchall(query, (limit,))
        return [
            {
                "id": row[0],
                "question": row[1],
                "answer": row[2],
                "context_ids": row[3].split(",") if row[3] else [],
                "created_date": row[4],
            }
            for row in rows
        ]

    def clear_history(self) -> bool:
        """Deletes all Q&A history."""
        logger.warning("Attempting to clear all QA history.")
        cursor = self._execute("DELETE FROM qa_history", commit=True)
        # Optionally reset sequence: self._execute("DELETE FROM sqlite_sequence WHERE name='qa_history'", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from qa_history table.")
        return cleared
