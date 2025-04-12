#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Base repository class providing common database operations.
"""

import logging
import sqlite3
from typing import List, Tuple, Optional

# Get database connection function from .connection
# Use relative import within the package
from ..connection import get_db

logger = logging.getLogger(__name__)

class BaseRepository:
    """Base class for database repositories."""

    def __init__(self):
        """Initializes the repository by getting a database connection."""
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
                try:
                    self._conn.rollback()
                except Exception as rollback_err:
                    logger.error(f"Error during rollback after query failure: {rollback_err}")
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
                 try:
                    self._conn.rollback()
                 except Exception as rollback_err:
                    logger.error(f"Error during rollback after executemany failure: {rollback_err}")
            return 0 