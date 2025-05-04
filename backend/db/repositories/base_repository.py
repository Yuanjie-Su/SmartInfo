#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Base Repository Module
Provides a common base for database repository classes using asyncpg
"""

import logging
import asyncpg
from typing import Any, List, Tuple, Optional, Dict, Union
from contextlib import asynccontextmanager

from db.connection import get_db_connection_context

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository for database operations using asyncpg."""

    def __init__(self, connection: Optional[asyncpg.Connection] = None):
        """
        Initializes the repository with an optional database connection override.
        This is primarily for testing purposes.
        :param connection: asyncpg.Connection (for overriding the default context manager)
        """
        # Store the connection override directly
        self._connection_override = connection

    def _get_connection_context(self):  # Removed async
        """
        Get the database connection context manager.
        Uses the override if provided, otherwise uses the default from db.connection.
        """
        if self._connection_override:
            # If an override connection is provided, return a simple context manager for it
            @asynccontextmanager
            async def override_context_manager():
                yield self._connection_override

            return override_context_manager()
        else:
            # Otherwise, use the standard context manager from the connection module
            return (
                get_db_connection_context()
            )  # Call the function to get the context manager instance

    async def _execute(self, query: str, params: Tuple = ()) -> Optional[str]:
        """
        Execute a query (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query string (using $1, $2 placeholders)
            params: Parameters for the query

        Returns:
            Status string from asyncpg on success.
            Raises exceptions on database errors.
        """
        try:
            async with self._get_connection_context() as conn:  # Removed await
                status_string = await conn.execute(query, *params)
                return status_string
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error executing query: {query} with params {params}. Error: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error during query execution: {e}")
            raise

    async def _executemany(self, query: str, params_list: List[Tuple]) -> bool:
        """
        Execute a batch query with multiple parameter sets.

        Args:
            query: SQL query string (using $1, $2 placeholders)
            params_list: List of parameter tuples for the query

        Returns:
            True if execution was successful (no exceptions).
            Raises exceptions on database errors.
        """
        try:
            async with self._get_connection_context() as conn:  # Removed await
                await conn.executemany(query, params_list)
                return True
        except asyncpg.PostgresError as e:
            logger.error(f"Error executing batch query: {query}. Error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during batch query execution: {e}")
            raise

    async def _fetchval(self, query: str, params: Tuple = ()) -> Optional[Any]:
        """
        Execute a query and fetch a single value.

        Args:
            query: SQL query string (using $1, $2 placeholders)
            params: Parameters for the query
        Returns:
            Single value from the result or None if no results.
            Raises exceptions on database errors.
        """
        try:
            async with self._get_connection_context() as conn:  # Removed await
                return await conn.fetchval(query, *params)
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error fetching value: {query} with params {params}. Error: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching value: {e}")
            raise

    async def _fetchone(
        self, query: str, params: Tuple = ()
    ) -> Optional[asyncpg.Record]:
        """
        Execute a query and fetch one result as an asyncpg.Record.

        Args:
            query: SQL query string (using $1, $2 placeholders)
            params: Parameters for the query

        Returns:
            Single row as an asyncpg.Record or None if no results.
            Raises exceptions on database errors.
        """
        try:
            async with self._get_connection_context() as conn:  # Removed await
                return await conn.fetchrow(query, *params)
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error fetching one row: {query} with params {params}. Error: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching one row: {e}")
            raise

    async def _fetchall(self, query: str, params: Tuple = ()) -> List[asyncpg.Record]:
        """
        Execute a query and fetch all results as a list of asyncpg.Record objects.

        Args:
            query: SQL query string (using $1, $2 placeholders)
            params: Parameters for the query

        Returns:
            List of rows as asyncpg.Record objects or empty list if no results.
            Raises exceptions on database errors.
        """
        try:
            async with self._get_connection_context() as conn:  # Removed await
                return await conn.fetch(query, *params)
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error fetching all rows: {query} with params {params}. Error: {e}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching all rows: {e}")
            raise
