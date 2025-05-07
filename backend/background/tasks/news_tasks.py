# File: backend/background/tasks/news_tasks.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery tasks for news processing
Handles background processing of news sources and articles,
while reporting progress through Redis Pub/Sub mechanism.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, List
import os  # Import os to get pid for logging
import redis.asyncio as redis  # Import Redis async client
import redis as sync_redis  # Import synchronous Redis client for chord callback

from celery import shared_task

# Import resources TYPE HINTS only, actual instances will be created within the task
from core.llm.pool import LLMClientPool
from db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    ApiKeyRepository,
)
from models import ApiKey

# Import the actual workflow function
from core.workflow.news_fetch import fetch_news

# Import DB connection management
from db.connection import init_db_connection, DatabaseConnectionManager

# Import ws_manager
from core.ws_manager import ws_manager

# Configure module-level logger
logger = logging.getLogger(__name__)

# Define maximum concurrency for processing sources within a batch task
MAX_CONCURRENT_SOURCES = 3


# --- Helper function to run async logic within the task ---
async def _run_batch_processing(
    task,  # Celery task instance for state updates
    source_ids: List[int],
    user_id: int,
    task_group_id: str,  # Added task_group_id
):
    """
    Main async function executed by asyncio.run() within the Celery task.
    Manages database connection, repositories, LLM client, and processes a batch of sources concurrently.
    Sends progress updates and errors via Redis Pub/Sub using the task_group_id as channel name.
    """
    pid = os.getpid()
    db_manager: Optional[DatabaseConnectionManager] = None
    llm_pool: Optional[LLMClientPool] = None
    news_repo: Optional[NewsRepository] = None
    source_repo: Optional[NewsSourceRepository] = None
    api_key_repo: Optional[ApiKeyRepository] = None
    redis_client = None

    # Define progress callback that publishes updates via Redis
    async def progress_callback(
        source_id: int,
        source_name: str,
        step: str,
        progress: float,
        details: str = "",
        items_count: int = 0,
    ):
        update_data = {
            "event": "source_progress",  # Event type for frontend
            "task_id": task.request.id,  # Include Celery task ID for context
            "source_id": source_id,
            "source_name": source_name,
            "step": step,
            "progress": progress,
            "message": details,
        }
        if items_count > 0:
            update_data["items_saved"] = items_count

        # Publish update to Redis instead of using ws_manager directly
        channel = f"task_progress:{task_group_id}"
        if redis_client:
            try:
                # Serialize the update data to JSON
                json_message = json.dumps(update_data)
                # Publish to Redis channel
                await redis_client.publish(channel, json_message)
                logger.debug(f"Published progress update to Redis channel {channel}")
            except Exception as e:
                logger.error(f"Failed to publish progress update to Redis: {e}")
        else:
            logger.warning("Redis client not available for progress updates")

        logger.info(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}) Progress: Source {source_id} ({source_name}): {step} - {progress:.1f}% - {details}"
        )

    try:
        # Initialize Redis client for publishing updates
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        redis_client = await redis.Redis.from_url(redis_url, decode_responses=True)
        logger.info(f"Redis client initialized for task {task.request.id}")

        # 1. Initialize DB connection manager and acquire connection context
        # Using "pool" mode with min/max size 1 is appropriate for a single task needing a connection.
        db_manager = await init_db_connection(
            db_connection_mode="pool",
            min_size=MAX_CONCURRENT_SOURCES,
            max_size=MAX_CONCURRENT_SOURCES,
        )

        # 2. Initialize Repositories with the acquired connection
        news_repo = NewsRepository()
        source_repo = NewsSourceRepository()
        api_key_repo = ApiKeyRepository()
        logger.info(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Repositories initialized."
        )

        # 3. Fetch and Validate Source Details
        source_details_to_process: List[Dict[str, Any]] = []
        for source_id in source_ids:
            source_record = await source_repo.get_by_id(source_id, user_id)
            if not source_record:
                logger.warning(
                    f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Source ID {source_id} not found or not owned by user {user_id}. Skipping."
                )
                # Report skipped status for this source via Redis
                await progress_callback(
                    source_id=source_id,
                    source_name=f"Unknown Source (ID: {source_id})",
                    step="skipped",
                    progress=100,
                    details=f"源ID {source_id} 未找到或不属于用户 {user_id}",
                )
                continue
            source_details_to_process.append(dict(source_record))

        if not source_details_to_process:
            logger.warning(
                f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): No valid sources to process for user {user_id} in this batch."
            )
            # Send a completion message for this batch via Redis
            completion_data = {
                "event": "batch_task_completed",
                "task_id": task.request.id,
                "message": "No valid sources to process in this batch.",
                "items_saved": 0,
                "affected_source_ids": source_ids,  # Report which sources were intended for this batch
            }
            channel = f"task_progress:{task_group_id}"
            if redis_client:
                await redis_client.publish(channel, json.dumps(completion_data))

            return {
                "task_id": task.request.id,
                "task_group_id": task_group_id,
                "status": "SUCCESS",
                "processed_sources_count": 0,
                "successful_sources_count": 0,
                "failed_sources_count": 0,
                "items_saved_in_batch": 0,
                "message": "No valid sources to process in this batch.",
            }

        # 4. Initialize a single LLM Client for the batch
        llm_pool = await _get_user_llm_pool(user_id, api_key_repo)
        if llm_pool is None:
            logger.error(
                f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): No valid LLM API key found for user {user_id}. Cannot process batch."
            )
            # Send a failure message for the batch via Redis
            failure_data = {
                "event": "batch_task_failed",
                "task_id": task.request.id,
                "affected_source_ids": source_ids,  # Report which sources were intended for this batch
                "message": f"Celery task failed: No valid LLM API key found for user {user_id}",
            }
            channel = f"task_progress:{task_group_id}"
            if redis_client:
                await redis_client.publish(channel, json.dumps(failure_data))

            # Re-raise to mark the Celery task as FAILED
            raise Exception(f"No valid LLM API key found for user {user_id}")

        # 5. Process sources concurrently
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SOURCES)
        processing_tasks = []
        for source_details in source_details_to_process:
            processing_tasks.append(
                _process_single_source_concurrently(
                    semaphore=semaphore,
                    task=task,  # Pass task instance
                    source_details=source_details,
                    llm_pool=llm_pool,
                    news_repo=news_repo,
                    user_id=user_id,
                    progress_callback=progress_callback,  # Pass the modified callback
                )
            )

        logger.info(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Starting concurrent processing for {len(processing_tasks)} sources with concurrency {MAX_CONCURRENT_SOURCES}."
        )
        # Use return_exceptions=True to ensure all tasks are attempted even if some fail
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)
        logger.info(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Concurrent processing finished."
        )

        # Aggregate results (optional, for logging or final task state)
        successful_count = sum(
            1 for r in results if isinstance(r, dict) and r.get("status") == "success"
        )
        error_count = len(results) - successful_count
        items_saved = sum(
            r.get("items_saved", 0)
            for r in results
            if isinstance(r, dict) and r.get("status") == "success"
        )

        logger.info(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Batch processing summary - Successful: {successful_count}, Errors: {error_count}, Items saved: {items_saved}"
        )

        # Send a completion message for this batch via Redis
        completion_data = {
            "event": "batch_task_completed",
            "task_id": task.request.id,
            "message": f"Batch processing completed. Successful: {successful_count}, Errors: {error_count}",
            "items_saved": items_saved,
            "affected_source_ids": source_ids,  # Report which sources were intended for this batch
        }
        channel = f"task_progress:{task_group_id}"
        if redis_client:
            await redis_client.publish(channel, json.dumps(completion_data))

        # Return structured dictionary for chord callback
        return {
            "task_id": task.request.id,
            "task_group_id": task_group_id,
            "status": "SUCCESS" if error_count == 0 else "COMPLETED_WITH_ERRORS",
            "processed_sources_count": len(source_details_to_process),
            "successful_sources_count": successful_count,
            "failed_sources_count": error_count,
            "items_saved_in_batch": items_saved,
            "message": f"Batch processing completed. Successful: {successful_count}, Errors: {error_count}",
        }

    except Exception as e:
        logger.exception(
            f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Unhandled error during batch async processing for user {user_id}: {e}"
        )
        # Send a failure message for the batch via Redis
        failure_data = {
            "event": "batch_task_failed",
            "task_id": task.request.id,
            "affected_source_ids": source_ids,  # Report which sources were intended for this batch
            "message": f"Celery task failed: {str(e)}",
        }
        try:
            channel = f"task_progress:{task_group_id}"
            if redis_client:
                await redis_client.publish(channel, json.dumps(failure_data))
        except Exception as cb_e:
            logger.error(
                f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Failed to send batch error state via Redis: {cb_e}"
            )
        # Re-raise to let the sync wrapper handle FAILURE state
        raise  # Crucially re-raise the exception

    finally:
        # Close Redis client
        if redis_client:
            try:
                await redis_client.close()
                logger.info(f"Redis client closed for task {task.request.id}")
            except Exception as redis_err:
                logger.error(f"Error closing Redis client: {redis_err}")

        # Ensure LLM client is closed
        if llm_pool:
            try:
                await llm_pool.close()
                logger.info(
                    f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): LLM pool closed in finally block."
                )
            except Exception as close_err:
                logger.error(
                    f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Error closing LLM pool in finally block: {close_err}"
                )

        # Ensure database connection is cleaned up
        if db_manager:
            try:
                await db_manager._cleanup()
                logger.info(
                    f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Database connection closed in finally block."
                )
            except Exception as close_err:
                logger.error(
                    f"[PID:{pid}] Task {task.request.id} (Group: {task_group_id}): Error closing database connection in finally block: {close_err}"
                )


async def _process_single_source_concurrently(
    semaphore: asyncio.Semaphore,
    task,  # Celery task instance
    source_details: Dict[str, Any],
    llm_pool: LLMClientPool,
    news_repo: NewsRepository,
    user_id: int,
    progress_callback: callable,  # Batch-level callback
) -> Dict[str, Any]:
    """
    Processes a single news source within the batch, managed by a semaphore.
    Calls the core workflow function and handles saving results.
    """
    pid = os.getpid()
    source_id = source_details["source_id"]
    url = source_details["url"]
    source_name = source_details["source_name"]
    category_id = source_details.get("category_id")
    category_name = source_details.get("category_name", "未知分类")

    # Create a source-specific progress callback that wraps the batch callback
    async def source_progress_callback(
        step: str, progress: float, details: str = "", items_count: int = 0
    ):
        await progress_callback(
            source_id=source_id,
            source_name=source_name,
            step=step,
            progress=progress,
            details=details,
            items_count=items_count,
        )

    async with semaphore:
        logger.info(
            f"[PID:{pid}] Task {task.request.id}: Starting processing for source {source_id} ({source_name}, User: {user_id})."
        )
        try:
            await source_progress_callback("preparing", 5, "准备抓取数据...")

            # Get existing URLs for this user to avoid duplicates
            exclude_links = await news_repo.get_all_urls(user_id)
            logger.info(
                f"[PID:{pid}] Task {task.request.id}: Source {source_id}: Found {len(exclude_links)} existing URLs for user {user_id}."
            )

            # Call the core workflow function
            fetch_result = None
            try:
                fetch_result = await fetch_news(
                    url=url,
                    llm_pool=llm_pool,
                    exclude_links=exclude_links,
                    progress_callback=source_progress_callback,
                )

            except Exception as e:
                logger.exception(
                    f"[PID:{pid}] Task {task.request.id}: Source {source_id}: Error during fetch_news: {e}"
                )
                await source_progress_callback("error", 0, f"抓取和分析错误: {str(e)}")
                return {
                    "source_id": source_id,
                    "status": "error",
                    "message": f"Error during fetch and analysis: {str(e)}",
                }

            # --- Process fetch_result ---
            if not fetch_result:
                await source_progress_callback(
                    "complete", 100, "完成处理，但未找到新内容"
                )
                return {
                    "source_id": source_id,
                    "status": "success",
                    "message": "No new content found",
                    "items_saved": 0,
                }

            # Add source and category info, and user ID
            for result_item in fetch_result:
                result_item["source_name"] = source_name
                result_item["category_name"] = category_name
                result_item["source_id"] = source_id
                result_item["category_id"] = category_id

            await source_progress_callback(
                "saving",
                95,
                f"正在保存 {len(fetch_result)} 个新闻项...",
                len(fetch_result),
            )

            # Save to database using user ID
            saved_count, skipped_count = await news_repo.add_batch(
                fetch_result, user_id
            )

            await source_progress_callback(
                "complete",
                100,
                f"成功处理并保存了 {saved_count} 个新闻项，跳过了 {skipped_count} 个新闻项",
                saved_count,
            )

            logger.info(
                f"[PID:{pid}] Task {task.request.id}: Source {source_id}: Successfully processed and saved {saved_count} items."
            )

            return {
                "source_id": source_id,
                "status": "success",
                "items_saved": saved_count,
                "items_skipped": skipped_count,
                "message": f"Successfully processed {saved_count} news items",
            }

        except Exception as e:
            logger.exception(
                f"[PID:{pid}] Task {task.request.id}: Source {source_id}: Unhandled error during concurrent processing: {e}"
            )
            # Ensure error state is reported for this specific source
            try:
                await source_progress_callback("error", 100, f"内部处理错误: {str(e)}")
            except Exception as cb_e:
                logger.error(
                    f"[PID:{pid}] Task {task.request.id}: Source {source_id}: Failed to update error state via callback: {cb_e}"
                )
            return {
                "source_id": source_id,
                "status": "error",
                "progress": 100,
                "message": f"Error processing source {source_details['source_name']}: {str(e)}",
            }


async def _get_user_llm_pool(
    user_id: int, api_key_repo: ApiKeyRepository
) -> Optional[LLMClientPool]:
    """
    Fetches user's API key configuration and instantiates an AsyncLLMClient.
    Returns None if no valid key is found.
    (Moved outside the main processing function for clarity)
    """
    # This repo instance uses the connection from the current task's context
    api_keys_data = await api_key_repo.get_all(user_id)

    if not api_keys_data:
        logger.warning(f"No API keys found for user {user_id}.")
        return None

    # Use the first valid API key found
    for key_data in api_keys_data:
        try:
            api_key = ApiKey.model_validate(dict(key_data))
            logger.info(f"Using API key ID {api_key.id} for user {user_id}")
            return LLMClientPool(
                pool_size=MAX_CONCURRENT_SOURCES,
                base_url=api_key.base_url,
                api_key=api_key.api_key,
                model=api_key.model,
                context=api_key.context,
                max_output_tokens=api_key.max_output_tokens,
            )
        except Exception as e:
            logger.error(
                f"Failed to validate or instantiate LLM client for API key data: {key_data}. Error: {e}",
                exc_info=True,
            )
            continue  # Try the next key

    logger.warning(f"No valid API key configuration found for user {user_id}.")
    return None


# --- Celery Task Definition ---
@shared_task(bind=True, name="process_single_batch_task")
def process_single_batch_task(
    self, source_ids: List[int], user_id: int, task_group_id: str
):
    """
    Celery task to process a single batch of news source IDs for a specific user
    within a larger task group.
    Initializes dependencies and runs the async batch processing logic.

    Args:
        self: Celery task instance (injected by bind=True)
        source_ids: List of IDs of the news sources to process in this batch
        user_id: ID of the user who owns these sources
        task_group_id: The ID of the overall task group this batch belongs to

    Returns:
        Dict with summary of results for this batch
    """
    pid = os.getpid()
    logger.info(
        f"[PID:{pid}] Received single batch task {self.request.id} for source IDs: {source_ids} (User: {user_id}, Group: {task_group_id})"
    )

    try:
        # Use asyncio.run to execute the async logic in a new event loop
        result = asyncio.run(
            _run_batch_processing(
                task=self,  # Pass the task instance for state updates
                source_ids=source_ids,
                user_id=user_id,
                task_group_id=task_group_id,  # Pass the group ID
            )
        )
        # Return the structured result dict for the chord callback
        return result
    except Exception as e:
        # Error logging and sending the "batch_task_failed" event via Redis Pub/Sub
        # are handled within _run_batch_processing.
        # We just need to ensure the exception propagates to Celery
        # so it marks this specific task as FAILED.
        logger.exception(
            f"[PID:{pid}] Single batch task {self.request.id} (Group: {task_group_id}) failed ultimately: {e}"
        )
        # Re-raise so Celery marks this task as FAILED
        raise


@shared_task(name="finalize_news_fetch_group")
def finalize_news_fetch_group(results, task_group_id: str, user_id: int):
    """
    Chord callback task that runs after all batch tasks complete.
    Aggregates results from all batches and sends the final completion event.

    Args:
        results: List of dictionaries returned by each batch task
        task_group_id: The ID of the overall task group
        user_id: ID of the user who owns the sources

    Returns:
        Dictionary with summary of overall task group results
    """
    pid = os.getpid()
    logger.info(
        f"[PID:{pid}] Executing chord callback for task_group_id: {task_group_id}, user_id: {user_id}"
    )

    # Initialize aggregated statistics
    total_batches = len(results)
    total_processed_sources = 0
    total_successful_sources = 0
    total_failed_sources = 0
    total_items_saved = 0
    batch_statuses = []

    # Iterate through results and aggregate statistics
    for batch_result in results:
        # Check if result is a valid dictionary
        if not isinstance(batch_result, dict):
            logger.warning(
                f"[PID:{pid}] Invalid batch result in task_group {task_group_id}: {batch_result}"
            )
            continue

        total_processed_sources += batch_result.get("processed_sources_count", 0)
        total_successful_sources += batch_result.get("successful_sources_count", 0)
        total_failed_sources += batch_result.get("failed_sources_count", 0)
        total_items_saved += batch_result.get("items_saved_in_batch", 0)
        batch_statuses.append(batch_result.get("status", "UNKNOWN"))

    # Determine overall status
    if all(status == "SUCCESS" for status in batch_statuses):
        overall_status = "SUCCESS"
    elif any(
        status == "SUCCESS" or status == "COMPLETED_WITH_ERRORS"
        for status in batch_statuses
    ):
        overall_status = "PARTIAL_SUCCESS"
    else:
        overall_status = "FAILURE"

    # Construct the final message
    final_message_data = {
        "event": "overall_batch_completed",
        "task_group_id": task_group_id,
        "user_id": user_id,
        "overall_status": overall_status,
        "total_batches": total_batches,
        "total_processed_sources": total_processed_sources,
        "total_successful_sources": total_successful_sources,
        "total_failed_sources": total_failed_sources,
        "total_items_saved": total_items_saved,
        "message": f"News fetch group completed. Overall status: {overall_status}. "
        f"Processed {total_processed_sources} sources with {total_successful_sources} successful, "
        f"{total_failed_sources} failed, and {total_items_saved} items saved.",
    }

    # Publish to Redis using synchronous client
    try:
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        redis_client = sync_redis.Redis.from_url(redis_url, decode_responses=True)
        channel = f"task_progress:{task_group_id}"

        # Serialize and publish the message
        json_message = json.dumps(final_message_data)
        redis_client.publish(channel, json_message)

        logger.info(
            f"[PID:{pid}] Published overall completion message to Redis channel {channel} for task_group_id: {task_group_id}"
        )

        # Close Redis client
        redis_client.close()
    except Exception as e:
        logger.exception(
            f"[PID:{pid}] Failed to publish overall completion message to Redis for task_group_id: {task_group_id}: {e}"
        )

    # Return summary for Celery result backend
    return {
        "task_group_id": task_group_id,
        "overall_status": overall_status,
        "total_batches": total_batches,
        "total_items_saved": total_items_saved,
        "message": f"Task group {task_group_id} completed with status: {overall_status}",
    }
