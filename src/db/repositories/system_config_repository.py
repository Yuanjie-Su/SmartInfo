# src/db/repositories/system_config_repository.py
# -*- coding: utf-8 -*-

import logging
from typing import Dict, Optional

from src.db.schema_constants import SYSTEM_CONFIG_TABLE
from .base_repository import BaseRepository  # Uses the new QtSql BaseRepository

logger = logging.getLogger(__name__)


class SystemConfigRepository(BaseRepository):
    """Repository for system_config table operations using QSqlQuery."""

    def get_config(self, key: str) -> Optional[str]:
        """Gets a system config value by key."""
        query_str = (
            f"SELECT config_value FROM {SYSTEM_CONFIG_TABLE} WHERE config_key = ?"
        )
        result = self._fetchone(query_str, (key,))
        return result[0] if result else None

    def save_config(
        self, key: str, value: str, description: Optional[str] = None
    ) -> bool:
        """Saves or updates a system config value."""
        # Use SQLite's ON CONFLICT clause
        query_str = f"""
            INSERT INTO {SYSTEM_CONFIG_TABLE} (config_key, config_value, description)
            VALUES (?, ?, ?)
            ON CONFLICT(config_key)
            DO UPDATE SET
                config_value = excluded.config_value,
                description = COALESCE(excluded.description, description)
        """
        query = self._execute(query_str, (key, value, description), commit=True)

        saved = query is not None  # Check if execution succeeded
        if saved:
            # numRowsAffected might be 0 or 1 for ON CONFLICT
            logger.info(f"Saved/Updated system config key '{key}'.")
        else:
            logger.error(f"Failed to save/update system config key '{key}'.")
        return saved

    def get_all_configs(self) -> Dict[str, str]:
        """Gets all system configurations."""
        query_str = f"SELECT config_key, config_value FROM {SYSTEM_CONFIG_TABLE}"
        rows = self._fetchall(query_str)
        return {row[0]: row[1] for row in rows}

    def delete_config(self, key: str) -> bool:
        """Deletes a system config key."""
        query_str = f"DELETE FROM {SYSTEM_CONFIG_TABLE} WHERE config_key = ?"
        query = self._execute(query_str, (key,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted system config key '{key}'.")
            else:
                logger.warning(f"Could not delete config key '{key}' (not found?).")
            return deleted
        return False  # Execution failed

    def delete_all(self) -> bool:
        """Deletes all system config keys."""
        logger.warning("Attempting to clear all system configuration using QtSql.")
        # Manual transaction management
        if not self._db.transaction():
            logger.error("Failed to start transaction for delete_all system config.")
            return False

        query_del = self._execute(f"DELETE FROM {SYSTEM_CONFIG_TABLE}", commit=False)
        # System config likely doesn't need auto-increment reset, but include if it does have an INTEGER PRIMARY KEY rowid
        # query_seq = self._execute(f"DELETE FROM sqlite_sequence WHERE name=?", (SYSTEM_CONFIG_TABLE,), commit=False)
        # cleared = query_del is not None and query_seq is not None
        cleared = query_del is not None  # Assuming no sequence reset needed

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for delete_all system config: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {SYSTEM_CONFIG_TABLE} table.")
        else:
            logger.error(
                f"Failed to clear system configuration from {SYSTEM_CONFIG_TABLE}. Rolling back."
            )
            self._db.rollback()

        return cleared
