# src/db/repositories/qa_repository.py
# -*- coding: utf-8 -*-

import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.db.schema_constants import QA_HISTORY_TABLE
from .base_repository import BaseRepository  # Uses the new QtSql BaseRepository

logger = logging.getLogger(__name__)


class QARepository(BaseRepository):
    """Repository for qa_history table operations using QSqlQuery."""

    def add_qa(
        self, question: str, answer: str, context_ids_str: Optional[str] = None
    ) -> Optional[int]:
        """Adds a new Q&A history entry."""
        now_str = datetime.now().isoformat()
        sql = f"""INSERT INTO {QA_HISTORY_TABLE} (question, answer, context_ids, created_date)
                VALUES (?, ?, ?, ?)"""
        # Ensure context_ids_str is None if empty or just whitespace
        params = (
            question,
            answer,
            context_ids_str if context_ids_str and context_ids_str.strip() else None,
            now_str,
        )

        query = self._execute(sql, params, commit=True)

        if query:
            last_id = self._get_last_insert_id(query)
            if last_id is not None:
                logger.info(f"Added QA history entry with ID {last_id}")
                return (
                    int(last_id)
                    if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                    else None
                )
            else:
                logger.error("Failed to retrieve lastInsertId after adding QA history.")
                return None
        else:
            logger.error("Failed to execute add QA history entry.")
            return None

    def get_all_qa(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves Q&A history entries with pagination."""
        sql = f"""SELECT id, question, answer, context_ids, created_date
                   FROM {QA_HISTORY_TABLE}
                   ORDER BY created_date DESC
                   LIMIT ? OFFSET ?"""
        rows = self._fetchall(sql, (limit, offset))  # _fetchall returns List[Tuple]
        history = []
        for row in rows:
            # Indices match the SELECT statement
            history.append(
                {
                    "id": row[0],
                    "question": row[1],
                    "answer": row[2],
                    "context_ids": row[3],  # Keep as string or None
                    "created_date": row[4],  # ISO format string
                }
            )
        return history

    def clear_history(self) -> bool:
        """Deletes all Q&A history."""
        logger.warning("Attempting to clear all QA history using QtSql.")
        # Manual transaction management
        if not self._db.transaction():
            logger.error("Failed to start transaction for clear_history.")
            return False

        query_del = self._execute(f"DELETE FROM {QA_HISTORY_TABLE}", commit=False)
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name=?",
            (QA_HISTORY_TABLE,),
            commit=False,
        )

        cleared = query_del is not None and query_seq is not None

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for clear_history: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {QA_HISTORY_TABLE} table.")
        else:
            logger.error(
                f"Failed to clear QA history from {QA_HISTORY_TABLE}. Rolling back."
            )
            self._db.rollback()

        return cleared

    def delete_qa(self, qa_id: int) -> bool:
        """Deletes a specific Q&A entry by ID."""
        sql = f"DELETE FROM {QA_HISTORY_TABLE} WHERE id = ?"
        query = self._execute(sql, (qa_id,), commit=True)
        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(
                    f"Deleted QA history entry with ID {qa_id} from {QA_HISTORY_TABLE}."
                )
            else:
                logger.warning(
                    f"Could not delete QA history entry with ID {qa_id} from {QA_HISTORY_TABLE} (not found?)."
                )
            return deleted
        return False  # Execution failed
