#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Base repository class providing common async database operations using aiosqlite.
Provides a base class for all database repositories.
"""

import logging
import aiosqlite
from typing import List, Tuple, Optional, Any # Added Any

# Get database connection function from .connection
from ..connection import get_db

logger = logging.getLogger(__name__)

class BaseRepository:
    """Base class for async database repositories."""

    # Option 1: Get connection in each method (simpler, relies on global get_db)
    # Option 2: Pass connection during init (requires changes in service instantiation)
    # Let's use Option 1 for simplicity here.

    async def _execute(
        self, query: str, params: tuple = (), commit: bool = False
    ) -> Optional[aiosqlite.Cursor]:
        """Executes a query asynchronously and returns the cursor."""
        conn = None # Initialize conn to None
        cursor = None # Initialize cursor to None
        try:
            conn = await get_db()
            # Use execute for DML (INSERT, UPDATE, DELETE) and DDL (CREATE, ALTER)
            # Use executescript for multiple statements (like table creation if needed separately)
            cursor = await conn.execute(query, params)
            if commit:
                await conn.commit()
            # Returning the cursor directly might lead to issues if the connection
            # is used elsewhere before the cursor is closed.
            # It's often better to fetch results here or use context managers.
            # However, to keep the structure similar, we return it, but be cautious.
            # Caller should handle potential errors and resource cleanup.
            # Let's return rowcount or lastrowid for write operations instead.
            if commit:
                return cursor # Return cursor mainly for rowcount/lastrowid access after commit
            else:
                # For SELECTs, fetchone/fetchall will be used, which get their own cursor
                return cursor # Return cursor for fetch methods to use
        except aiosqlite.Error as e:
            logger.error(
                f"DB Error executing query: {query} with params {params}. Error: {e}",
                exc_info=True,
            )
            if conn and commit: # Check if conn exists before rollback
                try:
                    await conn.rollback()
                except Exception as rollback_err:
                    logger.error(f"Error during rollback after query failure: {rollback_err}")
            # Don't close cursor here if returning it, caller might need it
            return None
        # No finally block to close cursor, as it might be needed by fetchone/fetchall

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[Tuple]:
        """Executes a query and fetches one row asynchronously."""
        conn = None
        cursor = None
        try:
            conn = await get_db()
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            await cursor.close() # Close cursor after fetching
            return row
        except aiosqlite.Error as e:
            logger.error(
                f"DB Error fetching one: {query} with params {params}. Error: {e}",
                exc_info=True,
            )
            if cursor:
                await cursor.close()
            return None

    async def _fetchall(self, query: str, params: tuple = ()) -> List[Tuple]:
        """Executes a query and fetches all rows asynchronously."""
        conn = None
        cursor = None
        try:
            conn = await get_db()
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            await cursor.close() # Close cursor after fetching
            return rows
        except aiosqlite.Error as e:
            logger.error(
                f"DB Error fetching all: {query} with params {params}. Error: {e}",
                exc_info=True,
            )
            if cursor:
                await cursor.close()
            return []

    async def _executemany(
        self, query: str, params_list: List[tuple], commit: bool = True
    ) -> int:
        """Executes a query with multiple parameter sets asynchronously."""
        conn = None
        cursor = None
        try:
            conn = await get_db()
            # Use executemany for bulk operations
            cursor = await conn.executemany(query, params_list)
            rowcount = cursor.rowcount
            await cursor.close() # Close cursor after executemany
            if commit:
                await conn.commit()
            return rowcount
        except aiosqlite.Error as e:
            logger.error(f"DB Error executing many: {query}. Error: {e}", exc_info=True)
            if conn and commit: # Check if conn exists
                 try:
                    await conn.rollback()
                 except Exception as rollback_err:
                    logger.error(f"Error during rollback after executemany failure: {rollback_err}")
            if cursor: # Check if cursor exists
                await cursor.close()
            return 0