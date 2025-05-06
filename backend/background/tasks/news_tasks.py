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

# Import resources TYPE HINTS only, actual instances come from celery_worker globals
from core.llm.client import AsyncLLMClient  # Import AsyncLLMClient directly
from db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    ApiKeyRepository,
)  # Import ApiKeyRepository
from models import ApiKey  # Import ApiKey model

# Import the actual workflow function
from core.workflow.news_fetch import fetch_news

# Configure module-level logger
logger = logging.getLogger(__name__)

# --- IMPORTANT ---
# Tasks will now access the process-specific globals defined in celery_worker.py

# Access the process-specific globals from celery_worker
# It's generally better practice to pass dependencies if possible, but for
# Celery process globals, accessing them directly is a common pattern.
# We import the worker module itself to access its globals.
from background import celery_worker


@shared_task(bind=True, name="process_source_url_task")
def process_source_url_task_celery(
    self, source_id: int, url: str, source_name: str, task_group_id: str, user_id: int
):
    """
    Celery task to process a single news source URL.
    Uses process-specific resources initialized via signals.

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
        f"[PID:{pid}] Starting task {self.request.id} for source URL: {url} (Source: {source_name}, ID: {source_id}, User: {user_id})"
    )

    # Initial state update
    self.update_state(
        state="PROGRESS",
        meta={
            "source_id": source_id,
            "source_name": source_name,
            "step": "initializing",
            "progress": 5,
            "message": f"开始处理源: {source_name}",
        },
    )

    # --- Verify Dependencies ---
    # Access the globals from the imported celery_worker module
    news_repo = celery_worker._process_news_repo
    source_repo = celery_worker._process_source_repo
    api_key_repo = celery_worker._process_api_key_repo  # Access ApiKeyRepository

    if not all((news_repo, source_repo, api_key_repo)):  # Check for api_key_repo
        error_message = f"[PID:{pid}] Task dependencies not available in this worker process. Setup might have failed."
        logger.error(error_message)
        self.update_state(
            state="FAILURE",
            meta={
                "source_id": source_id,
                "source_name": source_name,
                "step": "error",
                "progress": 0,
                "message": "内部错误：工作进程资源初始化失败",  # User-friendly message
            },
        )
        # Use Reject to signal the task should not be retried easily for this kind of error
        raise Reject(error_message, requeue=False)

    # --- Execute Async Logic ---
    try:
        # Get or create an event loop for this task execution within the sync worker process
        # loop = asyncio.get_event_loop() <--- Avoid this in tasks, it might get a closed loop
        # Instead, use asyncio.run() for the main async call within the task
        result = asyncio.run(
            _process_source_url_async(
                task=self,
                source_id=source_id,
                url=url,
                source_name=source_name,
                task_group_id=task_group_id,
                user_id=user_id,
                news_repo=news_repo,
                source_repo=source_repo,
                api_key_repo=api_key_repo,  # Pass api_key_repo
            )
        )
        # Final state is set within _process_source_url_async via progress_callback
        return result
    except Exception as e:
        logger.exception(
            f"[PID:{pid}] Error processing source {source_id} for user {user_id}: {e}"
        )
        self.update_state(
            state="FAILURE",
            meta={
                "source_id": source_id,
                "source_name": source_name,
                "step": "error",
                "progress": 0,
                "message": f"处理错误: {str(e)}",
            },
        )
        # Reraise the exception so Celery knows the task failed
        raise


async def _process_source_url_async(
    task,
    source_id: int,
    url: str,
    source_name: str,
    task_group_id: str,
    user_id: int,
    news_repo: NewsRepository,
    source_repo: NewsSourceRepository,
    api_key_repo: ApiKeyRepository,  # Receive api_key_repo
) -> Dict[str, Any]:
    """
    Async implementation of the source URL processing logic.
    Uses the dependencies passed from the sync task wrapper.

    Args:
        task: Celery task instance
        source_id: ID of the news source
        url: URL of the news source
        source_name: Human-readable name of the source
        task_group_id: Group identifier for related tasks
        user_id: ID of the user who owns this source
        news_repo: Repository for news operations
        source_repo: Repository for news source operations
        api_key_repo: Repository for API key operations
    """
    pid = os.getpid()  # Get PID for logging clarity
    try:
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

        await progress_callback("preparing", 10, "准备抓取数据...")

        # Get or create LLM client on demand using user's API key
        client = await _get_user_llm_client(user_id, api_key_repo)
        if client is None:
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
            await progress_callback(
                "error", 0, f"无法获取源 ID {source_id} (用户 ID {user_id}) 的详细信息"
            )
            # No need to raise Reject here, just return error status
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
            async with client as llm_client:
                fetch_result = await fetch_news(
                    url=url,
                    llm_client=llm_client,  # Use on-demand client
                    exclude_links=exclude_links,
                    progress_callback=progress_callback,
                )
        except Exception as e:
            logger.exception(
                f"[PID:{pid}] Task {task.request.id}: Error during fetch_news with LLM for source {source_id} (User: {user_id}): {e}"
            )
            await progress_callback("error", 0, f"抓取和分析错误: {str(e)}")
            return {
                "status": "error",
                "message": f"Error during fetch and analysis: {str(e)}",
            }

        if not fetch_result:
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
            result_item["user_id"] = user_id  # 添加用户ID到新闻项

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

    except Exception as e:
        # Log the error within the async function
        logger.exception(
            f"[PID:{pid}] Task {task.request.id}: Async processing error for source {source_id} (User: {user_id}): {e}"
        )
        # Update state via callback before raising
        try:
            await progress_callback("error", 0, f"处理错误: {str(e)}")
        except Exception as cb_e:
            logger.error(
                f"[PID:{pid}] Task {task.request.id}: Failed to update error state via callback: {cb_e}"
            )
        # Re-raise the exception to be caught by the sync wrapper
        raise


async def _get_user_llm_client(
    user_id: int, api_key_repo: ApiKeyRepository
) -> Optional[AsyncLLMClient]:
    """
    Fetches user's API key configuration and instantiates an AsyncLLMClient.
    Returns None if no valid key is found.
    """
    api_keys_data = await api_key_repo.get_all(user_id)

    if not api_keys_data:
        logger.warning(f"No API keys found for user {user_id}.")
        return None

    # Use the first valid API key found
    for key_data in api_keys_data:
        try:
            api_key = ApiKey.model_validate(key_data)
            logger.info(
                f"Using API key ID {api_key.id} for user {user_id} (Provider: {api_key.provider})."
            )
            # Instantiate AsyncLLMClient with user-specific config
            # Note: AsyncLLMClient expects base_url, api_key, model, etc.
            # These should come from the ApiKey model fields.
            # Assuming ApiKey model has fields like base_url, api_key, model, context, max_output_tokens etc.
            # You might need to map ApiKey fields to AsyncLLMClient parameters
            # based on the specific LLM provider (api_key.provider).
            # For simplicity, assuming generic fields match AsyncLLMClient params.
            # You might need more complex logic here based on provider.
            return AsyncLLMClient(
                base_url=api_key.base_url,
                api_key=api_key.api_key,
                model=api_key.model,
                context_window=api_key.context,  # Assuming 'context' field in ApiKey model
                max_output_tokens=api_key.max_output_tokens,  # Assuming 'max_output_tokens' field in ApiKey model
                # Add other parameters if needed, e.g., timeout, max_retries
            )
        except Exception as e:
            logger.error(
                f"Failed to validate or instantiate LLM client for API key data: {key_data}. Error: {e}",
                exc_info=True,
            )
            continue  # Try the next key

    logger.warning(f"No valid API key configuration found for user {user_id}.")
    return None
