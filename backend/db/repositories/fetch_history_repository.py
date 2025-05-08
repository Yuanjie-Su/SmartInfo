# File: /home/cator/project/SmartInfo/backend/db/repositories/fetch_history_repository.py
# backend/db/repositories/fetch_history_repository.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Fetch History Repository Module
Handles database operations for the fetch_history table.
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
import asyncpg
from datetime import date, datetime, timezone

from db.repositories.base_repository import BaseRepository
from db.schema_constants import FetchHistory, NewsSource

logger = logging.getLogger(__name__)


class FetchHistoryRepository(BaseRepository):
    """Repository for fetch_history table operations."""

    async def record_completion(
        self,
        user_id: int,
        source_id: int,
        items_saved_this_run: int,
        task_group_id: Optional[str] = None,
    ) -> bool:
        """
        Records a successful fetch completion (items_saved > 0) for a source on a given day.
        Uses UPSERT to either insert a new record or atomically increment the count for the day.

        Args:
            user_id: The user ID.
            source_id: The news source ID.
            items_saved_this_run: The number of items saved in this specific run.
            task_group_id: Optional task group ID for tracking.

        Returns:
            True if the operation was successful, False otherwise.
        """
        if items_saved_this_run <= 0:
            logger.debug(
                f"Skipping history record for source {source_id}, user {user_id} as items_saved_this_run is 0."
            )
            return True  # Not an error, just nothing to record

        current_date = date.today()
        current_timestamp = datetime.now(timezone.utc)

        query_str = f"""
            INSERT INTO {FetchHistory.TABLE_NAME} ( 
                {FetchHistory.USER_ID}, {FetchHistory.SOURCE_ID}, {FetchHistory.RECORD_DATE},
                {FetchHistory.ITEMS_SAVED_TODAY}, {FetchHistory.LAST_UPDATED_AT}, {FetchHistory.LAST_BATCH_TASK_GROUP_ID}
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT ({FetchHistory.USER_ID}, {FetchHistory.SOURCE_ID}, {FetchHistory.RECORD_DATE}) DO UPDATE SET
                {FetchHistory.ITEMS_SAVED_TODAY} = {FetchHistory.TABLE_NAME}.{FetchHistory.ITEMS_SAVED_TODAY} + EXCLUDED.{FetchHistory.ITEMS_SAVED_TODAY},
                {FetchHistory.LAST_UPDATED_AT} = EXCLUDED.{FetchHistory.LAST_UPDATED_AT},
                {FetchHistory.LAST_BATCH_TASK_GROUP_ID} = EXCLUDED.{FetchHistory.LAST_BATCH_TASK_GROUP_ID}
        """
        params = (
            user_id,
            source_id,
            current_date,
            items_saved_this_run,  # Insert this amount initially or add it on conflict
            current_timestamp,
            task_group_id,
        )

        try:
            status = await self._execute(query_str, params)
            # INSERT 0 1 or UPDATE 1 indicates success
            success = status is not None and (
                status.startswith("INSERT") or status.startswith("UPDATE")
            )
            if success:
                logger.info(
                    f"Recorded/Updated fetch history for source {source_id}, user {user_id}, date {current_date}. Added {items_saved_this_run} items. Status: {status}"
                )
            else:
                logger.warning(
                    f"UPSERT command for fetch history (Source: {source_id}, User: {user_id}, Date: {current_date}) executed but status was '{status}'."
                )
            # Return True even if status is unexpected, as long as no exception occurred
            return True
        except asyncpg.PostgresError as e:
            logger.error(
                f"Error recording fetch history for source {source_id}, user {user_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error recording fetch history for source {source_id}, user {user_id}: {e}"
            )
            return False

    async def get_history_by_date(
        self, user_id: int, record_date: date
    ) -> List[asyncpg.Record]:
        """
        Gets fetch history records for a specific user and date, joined with source name.

        Args:
            user_id: The user ID.
            record_date: The specific date (YYYY-MM-DD).

        Returns:
            List of asyncpg.Record objects including source_name.
        """
        query_str = f"""
            SELECT
                fh.{FetchHistory.SOURCE_ID},
                ns.{NewsSource.NAME},
                fh.{FetchHistory.RECORD_DATE},
                fh.{FetchHistory.ITEMS_SAVED_TODAY},
                fh.{FetchHistory.LAST_UPDATED_AT}
            FROM {FetchHistory.TABLE_NAME} fh
            JOIN {NewsSource.TABLE_NAME} ns ON fh.{FetchHistory.SOURCE_ID} = ns.{NewsSource.ID}
            WHERE fh.{FetchHistory.USER_ID} = $1 AND fh.{FetchHistory.RECORD_DATE} = $2
              AND ns.{NewsSource.USER_ID} = $1 -- Ensure source also belongs to user
            ORDER BY fh.{FetchHistory.LAST_UPDATED_AT} DESC
        """
        try:
            return await self._fetchall(query_str, (user_id, record_date))
        except Exception as e:
            logger.error(
                f"Error getting fetch history for user {user_id}, date {record_date}: {e}"
            )
            return []

    async def get_history_by_date_range(
        self, user_id: int, start_date: date, end_date: date
    ) -> List[asyncpg.Record]:
        """
        Gets fetch history records for a specific user within a date range, joined with source name.

        Args:
            user_id: The user ID.
            start_date: The start date (inclusive).
            end_date: The end date (inclusive).

        Returns:
            List of asyncpg.Record objects including source_name.
        """
        query_str = f"""
            SELECT
                fh.{FetchHistory.SOURCE_ID},
                ns.{NewsSource.NAME},
                fh.{FetchHistory.RECORD_DATE},
                fh.{FetchHistory.ITEMS_SAVED_TODAY},
                fh.{FetchHistory.LAST_UPDATED_AT}
            FROM {FetchHistory.TABLE_NAME} fh
            JOIN {NewsSource.TABLE_NAME} ns ON fh.{FetchHistory.SOURCE_ID} = ns.{NewsSource.ID}
            WHERE fh.{FetchHistory.USER_ID} = $1
              AND fh.{FetchHistory.RECORD_DATE} >= $2
              AND fh.{FetchHistory.RECORD_DATE} <= $3
              AND ns.{NewsSource.USER_ID} = $1 -- Ensure source also belongs to user
            ORDER BY fh.{FetchHistory.RECORD_DATE} DESC, fh.{FetchHistory.LAST_UPDATED_AT} DESC
        """
        try:
            return await self._fetchall(query_str, (user_id, start_date, end_date))
        except Exception as e:
            logger.error(
                f"Error getting fetch history for user {user_id}, range {start_date}-{end_date}: {e}"
            )
            return []
