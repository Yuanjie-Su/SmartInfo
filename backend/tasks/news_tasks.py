#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery tasks for news processing
Handles background processing of news sources and articles,
while reporting progress through Celery's task state mechanism.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

from celery import shared_task
from backend.core.llm import LLMClientPool
from backend.db.repositories import NewsRepository, NewsSourceRepository
from backend.core.workflow.news_fetch import fetch_news

# Configure module-level logger
logger = logging.getLogger(__name__)

# Global shared instances that will be set in the worker process
_llm_pool: Optional[LLMClientPool] = None
_news_repo: Optional[NewsRepository] = None
_source_repo: Optional[NewsSourceRepository] = None


def init_task_dependencies(
    llm_pool: LLMClientPool,
    news_repo: NewsRepository,
    source_repo: NewsSourceRepository,
):
    """
    Initialize shared dependencies for task execution.
    Called when the worker starts to set global instances.
    """
    global _llm_pool, _news_repo, _source_repo
    _llm_pool = llm_pool
    _news_repo = news_repo
    _source_repo = source_repo
    logger.info("Task dependencies initialized")


@shared_task(bind=True, name="process_source_url_task")
def process_source_url_task_celery(
    self, source_id: int, url: str, source_name: str, task_group_id: str
):
    """
    Celery task to process a single news source URL.

    This task:
    1. Fetches articles from the source URL
    2. Extracts content and metadata
    3. Analyzes content if needed
    4. Saves results to the database
    5. Reports progress through task state updates

    Args:
        self: Celery task instance (injected by bind=True)
        source_id: ID of the news source
        url: URL of the news source
        source_name: Human-readable name of the source
        task_group_id: Group identifier for related tasks

    Returns:
        Dict with summary of results
    """
    logger.info(
        f"Starting processing of source URL: {url} (Source: {source_name}, ID: {source_id})"
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

    # Verify dependencies are initialized
    if not all((_llm_pool, _news_repo, _source_repo)):
        error_message = "Task dependencies not initialized"
        logger.error(error_message)
        self.update_state(
            state="FAILURE",
            meta={
                "source_id": source_id,
                "source_name": source_name,
                "step": "error",
                "progress": 0,
                "message": error_message,
            },
        )
        return {"status": "error", "message": error_message}

    try:
        # This is a synchronous Celery task, but fetch_news is async
        # We need to run the async code in an event loop
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            _process_source_url_async(self, source_id, url, source_name, task_group_id)
        )
        return result
    except Exception as e:
        logger.exception(f"Error in process_source_url_task_celery: {e}")
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
        return {"status": "error", "message": str(e)}


async def _process_source_url_async(
    task, source_id: int, url: str, source_name: str, task_group_id: str
) -> Dict[str, Any]:
    """
    Async implementation of the source URL processing logic.
    This function is called within the Celery task and handles all the async operations.

    Args:
        task: The Celery task instance (for progress updates)
        source_id: ID of the news source
        url: URL of the news source
        source_name: Name of the source
        task_group_id: Group ID for related tasks

    Returns:
        Dict with summary of the processing results
    """
    try:
        # Define progress callback that updates Celery task state
        async def progress_callback(
            step: str, progress: float, details: str = "", items_count: int = 0
        ):
            """Progress callback function for fetch_news

            Args:
                step: Processing step name
                progress: Percentage complete (0-100)
                details: Description of current status
                items_count: Number of items processed
            """
            # Create meta data for task update
            meta = {
                "source_id": source_id,
                "source_name": source_name,
                "step": step,
                "progress": progress,
                "message": details,
            }

            if items_count > 0:
                meta["items_saved"] = items_count

            # Update task state in Celery
            task.update_state(state="PROGRESS", meta=meta)

            # Log to console
            logger.info(
                f"Source {source_id} ({source_name}): {step} - {progress:.1f}% - {details}"
            )

        # Update progress to preparing state
        await progress_callback("preparing", 10, "准备抓取数据...")

        # Get the source details from the database
        source_details = await _source_repo.get_by_id_as_dict(source_id)
        if not source_details:
            await progress_callback("error", 0, f"无法获取源 ID {source_id} 的详细信息")
            return {"status": "error", "message": f"Source ID {source_id} not found"}

        # Extract category information
        category_id = source_details.get("category_id")
        category_name = source_details.get("category_name")

        # Get existing URLs to avoid duplicates
        exclude_links = await _news_repo.get_all_urls()

        # Use progress callback to fetch news data
        fetch_result = await fetch_news(
            url=url,
            llm_pool=_llm_pool,
            exclude_links=exclude_links,
            progress_callback=progress_callback,
        )

        # Process the fetched results
        if not fetch_result:
            await progress_callback("complete", 100, "完成处理，但未找到新内容")
            return {
                "status": "success",
                "message": "No new content found",
                "items_saved": 0,
            }

        # Add source and category information to all result items
        for result_item in fetch_result:
            result_item["source_name"] = source_name
            result_item["category_name"] = category_name
            result_item["source_id"] = source_id
            result_item["category_id"] = category_id

        # Update progress to saving state
        await progress_callback(
            "saving",
            95,
            f"正在保存 {len(fetch_result)} 个新闻项...",
            len(fetch_result),
        )

        # Save to database
        saved_count, skipped_count = await _news_repo.add_batch(fetch_result)

        # Send completion notification
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
        logger.exception(f"处理 {url} 的新闻时出错: {e}")
        await progress_callback("error", 0, f"处理错误: {str(e)}")
        return {"status": "error", "message": str(e)}
