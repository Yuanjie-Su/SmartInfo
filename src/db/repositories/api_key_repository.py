# src/db/repositories/api_key_repository.py
# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from src.db.schema_constants import API_CONFIG_TABLE
from .base_repository import BaseRepository  # Uses the new QtSql BaseRepository

logger = logging.getLogger(__name__)


class ApiKeyRepository(BaseRepository):
    """Repository for api_config table operations using QSqlQuery."""

    def save_key(self, api_name: str, api_key: str) -> bool:
        """Saves or updates an API key."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # SQLite's ON CONFLICT clause works well here
        query_str = f"""
            INSERT INTO {API_CONFIG_TABLE} (api_name, api_key, created_date, modified_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_name) DO UPDATE SET
                api_key = excluded.api_key,
                modified_date = excluded.modified_date
        """
        # Execute and commit in one step via BaseRepository
        query = self._execute(query_str, (api_name, api_key, now, now), commit=True)

        saved = query is not None  # _execute returns None on failure
        if saved:
            # numRowsAffected might be 0 or 1 for ON CONFLICT, so just check execution success
            logger.info(f"Saved/Updated API key for '{api_name}'.")
        else:
            logger.error(f"Failed to save/update API key for '{api_name}'.")
        return saved

    def get_key(self, api_name: str) -> Optional[str]:
        """Gets an API key by name."""
        query_str = f"SELECT api_key FROM {API_CONFIG_TABLE} WHERE api_name = ?"
        result = self._fetchone(
            query_str, (api_name,)
        )  # _fetchone returns Tuple or None
        return result[0] if result else None

    def delete_key(self, api_name: str) -> bool:
        """Deletes an API key."""
        query_str = f"DELETE FROM {API_CONFIG_TABLE} WHERE api_name = ?"
        query = self._execute(query_str, (api_name,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted API key for '{api_name}'.")
            else:
                logger.warning(f"API key '{api_name}' not found or delete failed.")
            return deleted
        return False  # Execution failed

    def get_all_keys_info(self) -> List[Tuple[str, str, str]]:
        """Gets info (name, created, modified) for all keys."""
        query_str = (
            f"SELECT api_name, created_date, modified_date FROM {API_CONFIG_TABLE}"
        )
        # _fetchall returns List[Tuple]
        return self._fetchall(query_str)

    def delete_all(self) -> bool:
        """Deletes all API keys."""
        logger.warning("Attempting to clear all API keys using QtSql.")
        # Manual transaction management
        if not self._db.transaction():
            logger.error("Failed to start transaction for delete_all api keys.")
            return False

        query_del = self._execute(f"DELETE FROM {API_CONFIG_TABLE}", commit=False)
        # Note: Auto-increment reset for SQLite requires the table name
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name=?",
            (API_CONFIG_TABLE,),
            commit=False,
        )

        cleared = query_del is not None and query_seq is not None

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for delete_all api keys: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {API_CONFIG_TABLE} table.")
        else:
            logger.error(
                f"Failed to clear API keys from {API_CONFIG_TABLE}. Rolling back."
            )
            self._db.rollback()

        return cleared
