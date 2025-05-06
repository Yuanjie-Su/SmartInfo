# File: backend/background/tasks/news_tasks.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery tasks for news processing
Handles background processing of news sources and articles,
while reporting progress through Celery's task state mechanism.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
import os  # Import os to get pid for logging

from celery import shared_task
from celery.exceptions import Reject  # Import Reject for clean error handling

# Import resources TYPE HINTS only, actual instances will be created within the task
from core.llm.client import AsyncLLMClient
from db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    ApiKeyRepository,
)
from models import ApiKey

# Import the actual workflow function
from core.workflow.news_fetch import fetch_news

# Import DB connection management
from db.connection import init_db_connection

# Configure module-level logger
logger = logging.getLogger(__name__)


# --- Helper function to run async logic within the task ---
async def _run_source_processing(
    task,  # Celery task instance for state updates
    source_id: int,
    url: str,
    source_name: str,
    task_group_id: str,
    user_id: int,
):
    """
    Main async function executed by asyncio.run() within the Celery task.
    Manages database connection, repositories, and calls the processing logic.
    """
    pid = os.getpid()
    db_manager = None
    llm_client = None
    news_repo = None
    source_repo = None
    api_key_repo = None

    # Define progress callback that updates Celery task state
    async def progress_callback(
        step: str, progress: float, details: str = "", items_count: int = 0
    ):
        meta = {
            "source_id": source_id,
            "source_name": source_name,
            "step": step,
            "progress": progress,
            "message": details,
        }
        if items_count > 0:
            meta["items_saved"] = items_count
        task.update_state(state="PROGRESS", meta=meta)
        logger.info(
            f"[PID:{pid}] Task {task.request.id} Progress: Source {source_id} ({source_name}): {step} - {progress:.1f}% - {details}"
        )

    try:
        # 1. Initialize DB connection manager and acquire connection context
        # Using "single" mode is appropriate here as each task run gets its own connection.
        db_manager = await init_db_connection(
            db_connection_mode="pool", min_size=1, max_size=1
        )
        async with db_manager.get_db_connection_context() as conn:
            logger.info(
                f"[PID:{pid}] Task {task.request.id}: Database connection acquired."
            )

            # 2. Initialize Repositories with the acquired connection
            news_repo = NewsRepository(conn)
            source_repo = NewsSourceRepository(conn)
            api_key_repo = ApiKeyRepository(conn)
            logger.info(
                f"[PID:{pid}] Task {task.request.id}: Repositories initialized."
            )

            # 3. Call the actual processing logic
            # _perform_source_processing now does the main work
            result = await _perform_source_processing(
                task=task,
                source_id=source_id,
                url=url,
                source_name=source_name,
                task_group_id=task_group_id,
                user_id=user_id,
                news_repo=news_repo,
                source_repo=source_repo,
                api_key_repo=api_key_repo,
                progress_callback=progress_callback,  # Pass the callback
            )
            return result  # Return the final result dict

    except Exception as e:
        logger.exception(
            f"[PID:{pid}] Task {task.request.id}: Error during async processing for source {source_id} (User: {user_id}): {e}"
        )
        # Update state via callback before raising
        try:
            await progress_callback("error", 0, f"内部处理错误: {str(e)}")
        except Exception as cb_e:
            logger.error(
                f"[PID:{pid}] Task {task.request.id}: Failed to update error state via callback: {cb_e}"
            )
        # Re-raise to let the sync wrapper handle FAILURE state
        raise
    finally:
        # Cleanup is handled by the async context manager for the connection
        logger.info(
            f"[PID:{pid}] Task {task.request.id}: Async processing block finished."
        )


async def _get_user_llm_client(
    user_id: int, api_key_repo: ApiKeyRepository
) -> Optional[AsyncLLMClient]:
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
            return AsyncLLMClient(
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


async def _perform_source_processing(
    task,  # Celery task instance for state updates
    source_id: int,
    url: str,
    source_name: str,
    task_group_id: str,
    user_id: int,
    news_repo: NewsRepository,
    source_repo: NewsSourceRepository,
    api_key_repo: ApiKeyRepository,
    progress_callback: callable,  # Receive the callback
) -> Dict[str, Any]:
    """
    Performs the core news fetching and processing logic.
    (Previously _process_source_url_async)
    """
    pid = os.getpid()
    llm_client = None  # Initialize llm_client
    try:
        await progress_callback("preparing", 10, "准备抓取数据...")

        # Get or create LLM client on demand using user's API key
        llm_client = await _get_user_llm_client(user_id, api_key_repo)
        if llm_client is None:
            await progress_callback(
                "error", 0, f"用户 {user_id} 没有配置有效的 LLM API 密钥"
            )
            return {
                "status": "error",
                "message": f"No valid LLM API key found for user {user_id}",
            }

        # 获取带有用户ID的源详细信息
        source_record = await source_repo.get_by_id(source_id, user_id)
        if not source_record:
            # Ensure cleanup before returning
            if llm_client:
                await llm_client.close()

            await progress_callback(
                "error", 0, f"无法获取源 ID {source_id} (用户 ID {user_id}) 的详细信息"
            )
            return {
                "status": "error",
                "message": f"Source ID {source_id} not found for user {user_id}",
            }

        source_details = dict(source_record)
        category_id = source_details.get("category_id")
        category_name = source_details.get("category_name", "未知分类")

        # 获取该用户的所有现有URL
        exclude_links = await news_repo.get_all_urls(user_id)
        logger.info(
            f"[PID:{pid}] Task {task.request.id}: Found {len(exclude_links)} existing URLs for user {user_id}."
        )

        # Call the core workflow function (use the on-demand client)
        fetch_result = None
        try:
            fetch_result = await fetch_news(
                url=url,
                llm_client=llm_client,  # Pass the initialized client
                exclude_links=exclude_links,
                progress_callback=progress_callback,
            )

        except Exception as e:
            logger.exception(
                f"[PID:{pid}] Task {task.request.id}: Error during fetch_news for source {source_id} (User: {user_id}): {e}"
            )
            if llm_client:
                await llm_client.close()

            await progress_callback("error", 0, f"抓取和分析错误: {str(e)}")
            return {
                "status": "error",
                "message": f"Error during fetch and analysis: {str(e)}",
            }

        # --- Process fetch_result ---
        if not fetch_result:
            if llm_client:
                await llm_client.close()

            await progress_callback("complete", 100, "完成处理，但未找到新内容")
            return {
                "status": "success",
                "message": "No new content found",
                "items_saved": 0,
            }

        # 添加源和分类信息以及用户ID
        for result_item in fetch_result:
            result_item["source_name"] = source_name
            result_item["category_name"] = category_name
            result_item["source_id"] = source_id
            result_item["category_id"] = category_id

        await progress_callback(
            "saving", 95, f"正在保存 {len(fetch_result)} 个新闻项...", len(fetch_result)
        )

        # 使用用户ID保存到数据库
        saved_count, skipped_count = await news_repo.add_batch(fetch_result, user_id)

        await progress_callback(
            "complete",
            100,
            f"成功处理并保存了 {saved_count} 个新闻项，跳过了 {skipped_count} 个新闻项",
            saved_count,
        )

        return {
            "status": "success",
            "items_saved": saved_count,
            "items_skipped": skipped_count,
            "message": f"Successfully processed {saved_count} news items",
        }

    finally:
        # Ensure LLM client is closed if it was created and not closed by context manager
        if llm_client:
            try:
                await llm_client.close()
                logger.info(
                    f"[PID:{pid}] Task {task.request.id}: LLM client closed in finally block."
                )
            except Exception as close_err:
                logger.error(
                    f"[PID:{pid}] Task {task.request.id}: Error closing LLM client in finally block: {close_err}"
                )


# --- Celery Task Definition ---
@shared_task(bind=True, name="process_source_url_task")
def process_source_url_task_celery(
    self, source_id: int, url: str, source_name: str, task_group_id: str, user_id: int
):
    """
    Celery task to process a single news source URL.
    Initializes dependencies and runs the async processing logic for each task invocation.

    Args:
        self: Celery task instance (injected by bind=True)
        source_id: ID of the news source
        url: URL of the news source
        source_name: Human-readable name of the source
        task_group_id: Group identifier for related tasks
        user_id: ID of the user who owns this source

    Returns:
        Dict with summary of results
    """
    pid = os.getpid()
    logger.info(
        f"[PID:{pid}] Received task {self.request.id} for source URL: {url} (Source: {source_name}, ID: {source_id}, User: {user_id})"
    )

    # Initial state update
    self.update_state(
        state="PENDING",  # Changed to PENDING initially
        meta={
            "source_id": source_id,
            "source_name": source_name,
            "step": "initializing",
            "progress": 0,
            "message": f"任务已接收，准备处理源: {source_name}",
        },
    )

    try:
        # Use asyncio.run to execute the async logic in a new event loop
        result = asyncio.run(
            _run_source_processing(
                task=self,  # Pass the task instance for state updates
                source_id=source_id,
                url=url,
                source_name=source_name,
                task_group_id=task_group_id,
                user_id=user_id,
            )
        )
        # The final state (SUCCESS/FAILURE) should be set within the async logic via progress_callback
        # If the async function completes without error, Celery implicitly marks SUCCESS
        # If it raises an exception, Celery marks FAILURE.
        # We return the result dict which might contain details.
        return result
    except Exception as e:
        # Error logging and FAILURE state update are handled within _run_source_processing
        # or by Celery if the exception propagates out of asyncio.run()
        logger.exception(f"[PID:{pid}] Task {self.request.id} failed ultimately: {e}")
        # Reraise the exception so Celery marks the task as FAILED
        # The state update with error message should have already happened inside _run_source_processing
        raise
