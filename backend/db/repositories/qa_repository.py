#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
QA History Repository Module
"""

import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class QARepository(BaseRepository):
    """Repository for qa_history table operations."""

    def add_qa(
        self, question: str, answer: str, context_ids_str: Optional[str] = None
    ) -> Optional[int]:
        """Adds a new Q&A history entry. context_ids_str should be a comma-separated string of IDs."""
        now_str = datetime.now().isoformat()
        # Schema uses context_ids TEXT and created_date TEXT
        sql = """INSERT INTO qa_history (question, answer, context_ids, created_date)
                 VALUES (?, ?, ?, ?)"""
        # Ensure context_ids_str is None if empty or just whitespace
        params = (question, answer, context_ids_str if context_ids_str and context_ids_str.strip() else None, now_str)
        cursor = self._execute(sql, params, commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added QA history entry with ID {cursor.lastrowid}")
            return cursor.lastrowid
        else:
            logger.error("Failed to add QA history entry.")
            return None

    def get_all_qa(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves Q&A history entries with pagination."""
        # Select using schema columns context_ids and created_date
        sql = """SELECT id, question, answer, context_ids, created_date
                 FROM qa_history
                 ORDER BY created_date DESC
                 LIMIT ? OFFSET ?"""
        rows = self._fetchall(sql, (limit, offset))
        history = []
        for row in rows:
            # context_ids (row[3]) is just a string or None
            # created_date (row[4]) is an ISO format string
            history.append({
                "id": row[0],
                "question": row[1],
                "answer": row[2],
                "context_ids": row[3], # Keep as string or None
                "created_date": row[4]
            })
        return history

    def clear_history(self) -> bool:
        """Deletes all Q&A history."""
        logger.warning("Attempting to clear all QA history.")
        # Table name is handled by BaseRepository now, if implemented there, or needs to be specified
        cursor = self._execute(f"DELETE FROM {self.table_name}", commit=True)
        # Optionally reset sequence: self._execute("DELETE FROM sqlite_sequence WHERE name='qa_history'", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info(f"Cleared all data from {self.table_name} table.")
        else:
            logger.error(f"Failed to clear QA history from {self.table_name}.")
        return cleared

    def delete_qa(self, qa_id: int) -> bool:
        """Deletes a specific Q&A entry by ID."""
        sql = f"DELETE FROM {self.table_name} WHERE id = ?"
        cursor = self._execute(sql, (qa_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted QA history entry with ID {qa_id} from {self.table_name}.")
        else:
            logger.warning(f"Could not delete QA history entry with ID {qa_id} from {self.table_name} (not found?).")
        return deleted
