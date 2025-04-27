#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Base Repository Module
Provides a common base for database repository classes using aiosqlite
"""

import logging
import aiosqlite
from typing import Any, List, Tuple, Optional, Dict, Union

from backend.db.connection import get_db_connection

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository for database operations using aiosqlite."""

    def __init__(
        self, connection: Optional[aiosqlite.Connection] = None
    ):  # Accept optional connection
        """Initialize the repository with a database connection."""
        self._connection = connection  # Use provided connection if available

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get a database connection."""
        if self._connection is not None:  # Use the instance's connection if set
            return self._connection
        # Otherwise, use the global dependency-injected connection getter
        conn = await get_db_connection()
        if not conn:
            logger.error("Database connection manager has not been initialized.")
            raise RuntimeError("Database connection manager has not been initialized.")
        return conn

    async def _execute(
        self, query: str, params: Tuple = (), commit: bool = False
    ) -> Optional[aiosqlite.Cursor]:
        """
        Execute a query and optionally commit the transaction.

        Args:
            query: SQL query string
            params: Parameters for the query
            commit: Whether to commit the transaction after execution

        Returns:
            Cursor object or None if execution failed
        """
        conn = None
        cursor = None
        try:
            conn = await self._get_connection()
            cursor = await conn.cursor()
            await cursor.execute(query, params)

            if commit:
                await conn.commit()

            return cursor
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            if commit and conn:
                logger.warning("Rolling back transaction")
                await conn.rollback()
            return None

    async def _executemany(
        self, query: str, params_list: List[Tuple], commit: bool = False
    ) -> int:
        """
        Execute a batch query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples for the query
            commit: Whether to commit the transaction after execution

        Returns:
            Number of affected rows or 0 if execution failed
        """
        conn = None
        cursor = None
        try:
            conn = await self._get_connection()
            cursor = await conn.cursor()
            await cursor.executemany(query, params_list)

            if commit:
                await conn.commit()

            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error executing batch query: {e}")
            if commit and conn:
                logger.warning("Rolling back transaction")
                await conn.rollback()
            return 0

    async def _fetchone(self, query: str, params: Tuple = ()) -> Optional[Tuple]:
        """
        Execute a query and fetch one result.

        Args:
            query: SQL query string
            params: Parameters for the query

        Returns:
            Single row as a tuple or None if no results or execution failed
        """
        try:
            cursor = await self._execute(query, params)
            if cursor:
                return await cursor.fetchone()
            return None
        except Exception as e:
            logger.error(f"Error fetching one row: {e}")
            return None

    async def _fetchall(self, query: str, params: Tuple = ()) -> List[Tuple]:
        """
        Execute a query and fetch all results.

        Args:
            query: SQL query string
            params: Parameters for the query

        Returns:
            List of rows as tuples or empty list if no results or execution failed
        """
        try:
            cursor = await self._execute(query, params)
            if cursor:
                return await cursor.fetchall()
            return []
        except Exception as e:
            logger.error(f"Error fetching all rows: {e}")
            return []

    def _get_rows_affected(self, cursor: aiosqlite.Cursor) -> int:
        """
        Get the number of rows affected by the last query.

        Args:
            cursor: The cursor that executed the query

        Returns:
            Number of rows affected
        """
        if cursor:
            return cursor.rowcount
        return 0

    def _get_last_insert_id(self, cursor: aiosqlite.Cursor) -> Optional[int]:
        """
        Get the ID of the last inserted row.

        Args:
            cursor: The cursor that executed the query

        Returns:
            Last insert ID or None if not available
        """
        if cursor:
            return cursor.lastrowid
        return None

    def _dict_factory(self, cursor: aiosqlite.Cursor, row: Tuple) -> Dict[str, Any]:
        """Convert a row tuple to a dictionary mapping column names to values."""
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    async def _fetch_as_dict(
        self, query_str: str, params: Tuple = ()
    ) -> List[Dict[str, Any]]:
        """Execute a query and fetch all rows as dictionaries."""
        cursor = await self._execute(query_str, params)
        if cursor:
            # aiosqlite不支持直接设置row_factory，需要手动转换
            rows = await cursor.fetchall()
            description = cursor.description
            return [
                {description[i][0]: value for i, value in enumerate(row)}
                for row in rows
            ]
        return []

    async def _fetchone_as_dict(
        self, query_str: str, params: Tuple = ()
    ) -> Optional[Dict[str, Any]]:
        """Execute a query and fetch one row as dictionary."""
        results = await self._fetch_as_dict(query_str, params)
        return results[0] if results else None
