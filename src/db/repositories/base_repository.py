# src/db/repositories/base_repository.py
# -*- coding: utf-8 -*-

import logging
from typing import List, Tuple, Optional, Any, Sequence

from PySide6.QtSql import QSqlQuery

# Use relative import within the package
from ..connection import get_db

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base class for database repositories using QSqlQuery."""

    def __init__(self):
        """Initializes the repository by getting the QSqlDatabase connection."""
        self._db = get_db()  # Get the QSqlDatabase instance
        if not self._db or not self._db.isValid() or not self._db.isOpen():
            raise ConnectionError(
                "BaseRepository: Invalid or closed database connection."
            )

    def _execute(
        self, query_str: str, params: Sequence = (), commit: bool = False
    ) -> Optional[QSqlQuery]:
        """Executes a query and returns the QSqlQuery object."""
        query = QSqlQuery(self._db)
        query.prepare(query_str)

        # Bind parameters using positional binding (?)
        if isinstance(params, (list, tuple)):
            for i, param in enumerate(params):
                query.bindValue(i, param)

        logger.debug(f"Executing SQL: {query_str} with params: {params}")

        if commit:
            if not self._db.transaction():
                logger.error(
                    f"DB Error: Failed to start transaction. Error: {self._db.lastError().text()}"
                )
                return None

        success = query.exec()

        if not success:
            error = query.lastError()
            logger.error(
                f"DB Error executing query: {query_str} with params {params}. Error: {error.text()} (Type: {error.type()}, Number: {error.number()})",
                exc_info=False,  # Keep log cleaner unless DEBUG
            )
            if commit and self._db.driver().hasFeature(self._db.driver().Transactions):
                self._db.rollback()
                logger.info("Transaction rolled back due to query execution error.")
            return None
        else:
            if commit:
                if not self._db.commit():
                    logger.error(
                        f"DB Error: Failed to commit transaction. Error: {self._db.lastError().text()}"
                    )
                    self._db.rollback()  # Attempt rollback
                    return None
            return query

    def _fetchone(self, query_str: str, params: Sequence = ()) -> Optional[Tuple]:
        """Executes a query and fetches one row."""
        query = self._execute(query_str, params)
        if query and query.next():
            record = query.record()
            return tuple(query.value(i) for i in range(record.count()))
        return None

    def _fetchall(self, query_str: str, params: Sequence = ()) -> List[Tuple]:
        """Executes a query and fetches all rows."""
        query = self._execute(query_str, params)
        results = []
        if query:
            record = query.record()
            col_count = record.count()
            while query.next():
                results.append(tuple(query.value(i) for i in range(col_count)))
        return results

    def _executemany(
        self, query_str: str, params_list: List[Sequence], commit: bool = True
    ) -> int:
        """Executes a query with multiple parameter sets within a transaction."""
        if not params_list:
            return 0

        if commit:
            if not self._db.transaction():
                logger.error(
                    f"DB Error: Failed to start transaction for executemany. Error: {self._db.lastError().text()}"
                )
                return 0

        query = QSqlQuery(self._db)
        if not query.prepare(query_str):
            error = query.lastError()
            logger.error(
                f"DB Error preparing query for executemany: {query_str}. Error: {error.text()}"
            )
            if commit:
                self._db.rollback()
            return 0

        success_count = 0
        for params in params_list:
            # Bind parameters for this iteration
            if isinstance(params, (list, tuple)):
                for i, param in enumerate(params):
                    query.bindValue(i, param)

            if query.exec():
                success_count += 1
            else:
                error = query.lastError()
                logger.error(
                    f"DB Error during executemany (item failed): {query_str} with params {params}. Error: {error.text()}",
                    exc_info=False,
                )
                # Stop on first error and rollback
                if commit:
                    self._db.rollback()
                    logger.info(
                        "Transaction rolled back due to executemany item failure."
                    )
                return 0  # Indicate failure

        # If loop completes without error
        if commit:
            if not self._db.commit():
                logger.error(
                    f"DB Error: Failed to commit transaction after executemany. Error: {self._db.lastError().text()}"
                )
                self._db.rollback()
                return 0  # Indicate failure

        return success_count  # Return number of successful executions

    def _get_last_insert_id(self, query: QSqlQuery) -> Optional[Any]:
        """Gets the last inserted ID from a QSqlQuery object."""
        # Get the last insert ID
        last_id_variant = query.lastInsertId()

        # Check if it's None
        if last_id_variant is None:
            return None

        # Check if it's a QVariant type
        if hasattr(last_id_variant, "isValid"):
            if last_id_variant.isValid():
                # Try common types
                if last_id_variant.canConvert(int):
                    return last_id_variant.toInt()[0]  # toInt returns (value, ok)
                elif last_id_variant.canConvert(str):
                    return last_id_variant.toString()
                else:
                    return last_id_variant.value()  # Return raw QVariant value
            return None
        else:
            # If it's already a primitive type (like int), return it directly
            return last_id_variant

    def _get_rows_affected(self, query: QSqlQuery) -> int:
        """Gets the number of rows affected by the last query."""
        return query.numRowsAffected()
