# backend/db/repositories/qa_repository.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Question and Answer History Repository Module (Async)
Provides data access operations for the qa_history table.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class QARepository(BaseRepository):
    """Repository for qa_history table operations."""

    def _row_to_dict(self, row: Tuple) -> Optional[Dict[str, Any]]:
        """Converts a database row tuple to a dictionary."""
        if not row:
            return None
        # Match the order of columns in the SELECT statements
        return {
            "id": row[0],
            "question": row[1],
            "answer": row[2],
            "context_ids": row[3], # Should be stored as JSON string, e.g., "[]"
            "created_date": row[4],
        }

    async def add_qa(self, question: str, answer: str, context_ids_json: str = "[]") -> Optional[int]:
        """Adds a new Q&A entry."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO qa_history (question, answer, context_ids, created_date)
            VALUES (?, ?, ?, ?)
        """
        cursor = await self._execute(query, (question, answer, context_ids_json, now), commit=True)
        if cursor and cursor.lastrowid:
            logger.info(f"Added QA history entry with ID {cursor.lastrowid}.")
            return cursor.lastrowid
        logger.error("Failed to add QA history entry.")
        return None

    async def get_all_qa(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Gets Q&A history entries with pagination."""
        query = """
             SELECT id, question, answer, context_ids, created_date
             FROM qa_history
             ORDER BY created_date DESC, id DESC
             LIMIT ? OFFSET ?
         """
        rows = await self._fetchall(query, (limit, offset))
        return [self._row_to_dict(row) for row in rows if row]

    async def get_by_id(self, qa_id: int) -> Optional[Dict[str, Any]]:
        """Gets a specific Q&A history item by ID."""
        query = """
             SELECT id, question, answer, context_ids, created_date
             FROM qa_history
             WHERE id = ?
         """
        row = await self._fetchone(query, (qa_id,))
        return self._row_to_dict(row)

    async def delete_qa(self, qa_id: int) -> bool:
        """Deletes a specific Q&A entry by its ID."""
        query = "DELETE FROM qa_history WHERE id = ?"
        cursor = await self._execute(query, (qa_id,), commit=True)
        deleted = cursor.rowcount > 0 if cursor else False
        if deleted:
            logger.info(f"Deleted QA history entry ID {qa_id}.")
        return deleted

    async def clear_history(self) -> bool:
        """Clears all Q&A history."""
        logger.warning("Attempting to clear all QA history.")
        # Reset auto-increment separately
        await self._execute("DELETE FROM sqlite_sequence WHERE name='qa_history'", commit=False)
        cursor = await self._execute("DELETE FROM qa_history", commit=True)
        cleared = cursor is not None
        if cleared:
            logger.info("Cleared all data from qa_history table.")
        return cleared