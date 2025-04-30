#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
NewsService Module
- Coordinates retrieval, processing, analysis, and storage of news content.
- Utilizes an LLM for link extraction and in-depth content summarization.
"""

import json
import logging
import asyncio
import re
import uuid
from typing import List, Dict, Optional, Tuple, Callable, Any, Union, AsyncGenerator
from urllib.parse import urljoin

import aiohttp
from fastapi import BackgroundTasks

# Crawler for asynchronous HTTP requests
from backend.core.crawler import (
    AiohttpCrawler,
    PlaywrightCrawler,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
)

from backend.core.workflow.news_fetch import fetch_news

# Repository interfaces for database operations
from backend.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)

# Client to interact with the LLM API
from backend.core.llm import LLMClientPool

# WebSocket manager for real-time updates
from backend.core.ws_manager import ws_manager

# Utilities for processing content and LLM output
from backend.utils.markdown_utils import (
    clean_markdown_links,
    strip_markdown_divider,
    strip_markdown_links,
)
from backend.utils.parse import parse_json_from_text
from backend.utils.token_utils import get_token_size
from backend.utils.html_utils import (
    clean_and_format_html,
    extract_metadata_from_article_html,
)
from backend.utils.text_utils import get_chunks
from backend.utils.prompt import (
    SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS,
    SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
    SYSTEM_PROMPT_ANALYZE_CONTENT,
)

# Configure module-level logger
logger = logging.getLogger(__name__)

# Constants for LLM model and token limits
DEFAULT_MODEL = "deepseek-v3-250324"
MAX_OUTPUT_TOKENS = 16384  # Max tokens for LLM output
MAX_INPUT_TOKENS = 131072 - 2 * MAX_OUTPUT_TOKENS


class NewsService:
    """
    Service class responsible for:
    - Fetching and cleaning HTML content.
    - Converting to Markdown and chunking large texts.
    - Extracting article links via LLM.
    - Crawling extracted links for sub-content.
    - Performing LLM-driven content analysis.
    - Parsing analysis results and saving to database.
    - Providing CRUD operations for news items, sources, and categories.
    """

    def __init__(
        self,
        news_repo: NewsRepository,
        source_repo: NewsSourceRepository,
        category_repo: NewsCategoryRepository,
    ):
        # Initialize database repository interfaces
        self._news_repo = news_repo
        self._source_repo = source_repo
        self._category_repo = category_repo
        self._llm_pool: Optional[LLMClientPool] = (
            None  # Will be set later by set_llm_pool method
        )

    def set_llm_pool(self, llm_pool: LLMClientPool):
        """Set the LLM client pool after initialization"""
        self._llm_pool = llm_pool
        logger.info("LLM client pool set for NewsService")

    # -------------------------------------------------------------------------
    # Public CRUD Methods (Pass-through to Repositories)
    # -------------------------------------------------------------------------
    # --- News Item Methods ---
    async def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Get a news item by ID"""
        return await self._news_repo.get_by_id_as_dict(news_id)

    async def get_all_news(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all news items with pagination"""
        return await self._news_repo.get_all_as_dict(limit, offset)

    async def get_news_with_filters(
        self,
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        has_analysis: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get news items with filters"""
        return await self._news_repo.get_news_with_filters_as_dict(
            category_id=category_id,
            source_id=source_id,
            analyzed=has_analysis,
            page=page,
            page_size=page_size,
            search_term=search_term,
        )

    async def update_news(
        self, news_id: int, news_item: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a news item. Not implemented yet."""
        # TODO: Implement news update logic
        return None

    async def delete_news(self, news_id: int) -> bool:
        """Delete a news item."""
        return await self._news_repo.delete(news_id)

    async def clear_all_news(self) -> bool:
        """Clear all news items."""
        return await self._news_repo.clear_all()

    # --- Category Methods ---
    async def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all categories"""
        return await self._category_repo._fetch_as_dict(
            """
            SELECT id, name FROM news_category
            """
        )

    async def get_all_categories_with_counts(self) -> List[Dict[str, Any]]:
        """Get all categories with news item counts"""
        return await self._category_repo.get_with_source_count_as_dict()

    async def get_category_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Get a category by ID"""
        return await self._category_repo.get_by_id_as_dict(category_id)

    async def add_category(self, name: str) -> Optional[int]:
        """Add a new category."""
        return await self._category_repo.add(name)

    async def create_category(
        self, category_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a new category using data from a dictionary (typically from a Pydantic model)"""
        name = category_data.get("name", "").strip()
        if not name:
            return None

        category_id = await self._category_repo.add(name)
        if not category_id:
            return None

        # Return a dictionary with the created category data
        return {"id": category_id, "name": name}

    async def update_category(self, category_id: int, new_name: str) -> bool:
        """Update a category name."""
        return await self._category_repo.update(category_id, new_name)

    async def update_category_from_dict(
        self, category_id: int, category_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a category using data from a dictionary (typically from a Pydantic model)"""
        new_name = category_data.get("name", "").strip()
        if not new_name:
            return None

        success = await self._category_repo.update(category_id, new_name)
        if not success:
            return None

        # Return the updated category data
        category = await self._category_repo.get_by_id(category_id)
        if not category:
            return None

        return {"id": category[0], "name": category[1]}

    async def delete_category(self, category_id: int) -> bool:
        """Delete a category."""
        # Note: This will cascade delete all sources in this category
        return await self._category_repo.delete(category_id)

    # --- Source Methods ---
    async def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get all news sources with category information"""
        return await self._source_repo.get_all_as_dict()

    async def get_sources_by_category_id(
        self, category_id: int
    ) -> List[Dict[str, Any]]:
        """Get all news sources for a specific category"""
        return await self._source_repo.get_by_category_as_dict(category_id)

    async def get_source_by_id(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get a news source by ID with category information"""
        return await self._source_repo.get_by_id_as_dict(source_id)

    async def add_source(
        self, name: str, url: str, category_name: str
    ) -> Optional[int]:
        """Add a news source.
        Creates the category if it doesn't exist."""
        # First get or create the category
        category = await self._category_repo.get_by_name(category_name)
        if category:
            category_id = category[0]
        else:
            category_id = await self._category_repo.add(category_name)
            if not category_id:
                logger.error(f"Failed to create category: {category_name}")
                return None

        # Now add the source
        return await self._source_repo.add(name, url, category_id)

    async def update_source(
        self, source_id: int, name: str, url: str, category_name: str
    ) -> bool:
        """Update a news source.
        Creates the category if it doesn't exist."""
        # First get or create the category
        category = await self._category_repo.get_by_name(category_name)
        if category:
            category_id = category[0]
        else:
            category_id = await self._category_repo.add(category_name)
            if not category_id:
                logger.error(f"Failed to create category: {category_name}")
                return False

        # Now update the source
        return await self._source_repo.update(source_id, name, url, category_id)

    async def delete_source(self, source_id: int) -> bool:
        """Delete a news source."""
        return await self._source_repo.delete(source_id)

    async def update_news_analysis(self, news_id: int, analysis_text: str) -> bool:
        """Update the analysis field of a news item."""
        return await self._news_repo.update_analysis(news_id, analysis_text)

    async def create_source(
        self, source_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a news source from dictionary data"""
        # Extract required fields
        name = source_data.get("name", "").strip()
        url = source_data.get("url", "").strip()
        category_id = source_data.get("category_id")

        # Validate required fields
        if not name or not url or not category_id:
            logger.warning("Missing required fields for source creation")
            return None

        # Check if source with name or URL already exists
        if await self._source_repo.exists_by_name(name):
            logger.warning(f"Source with name '{name}' already exists")
            return None

        if await self._source_repo.exists_by_url(url):
            logger.warning(f"Source with URL '{url}' already exists")
            return None

        # Add the source to the database
        source_id = await self._source_repo.add(
            name=name, url=url, category_id=category_id
        )
        if not source_id:
            logger.error("Failed to add source to database")
            return None

        # Return the newly created source
        return await self.get_source_by_id(source_id)

    async def fetch_sources_in_background(
        self,
        source_ids: List[int],
        task_group_id: str,
        background_tasks: BackgroundTasks,
    ):
        """
        Schedule background tasks to fetch and process news from multiple sources.

        Args:
            source_ids: List of source IDs to process
            task_group_id: Unique identifier for this batch of tasks
            background_tasks: FastAPI BackgroundTasks object to schedule tasks

        Returns:
            None - tasks are scheduled in the background
        """
        if not source_ids:
            logger.warning(f"No source IDs provided for task group {task_group_id}")
            return

        # 发送整体任务开始进度更新
        await ws_manager.send_update(
            task_group_id,
            {
                "task_group_id": task_group_id,
                "status": "initializing",
                "progress": 0,
                "message": f"初始化 {len(source_ids)} 个数据源的抓取任务",
                "total_sources": len(source_ids),
                "completed_sources": 0,
            },
        )

        logger.info(
            f"Scheduling background tasks for {len(source_ids)} sources in task group {task_group_id}"
        )

        # Schedule a task for each source
        for source_id in source_ids:
            try:
                # Get source details
                source = await self._source_repo.get_by_id(source_id)
                if not source:
                    # 使用进度回调发送错误信息
                    progress_callback = await self._create_progress_callback(
                        source_id,
                        f"Unknown Source (ID: {source_id})",
                        task_group_id,
                    )
                    await progress_callback("error", 0, f"源ID {source_id} 未找到")
                    continue

                # Extract required details
                url = source[2]  # URL is at index 2
                source_name = source[1]  # Name is at index 1

                # Add the background task
                background_tasks.add_task(
                    self._process_source_url_task,
                    source_id,
                    url,
                    source_name,
                    task_group_id,
                )

                logger.info(
                    f"Scheduled task for source: {source_name} (ID: {source_id})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to schedule task for source ID {source_id}: {e}",
                    exc_info=True,
                )
                # 使用进度回调发送错误信息
                progress_callback = await self._create_progress_callback(
                    source_id, f"Unknown Source (ID: {source_id})", task_group_id
                )
                await progress_callback("error", 0, f"调度任务失败: {str(e)}")

    async def _process_source_url_task(
        self,
        source_id: int,
        url: str,
        source_name: str,
        task_group_id: str,
    ):
        """
        Process a single source URL as a background task.

        This implements the full multi-step pipeline:
        1. Initial crawl of the source URL
        2. HTML cleaning
        3. LLM call for link extraction
        4. Crawling extracted article links
        5. LLM call for content analysis/summarization
        6. Saving results to the database
        7. Final update

        Args:
            source_id: ID of the news source
            url: URL of the news source
            source_name: Name of the news source
            task_group_id: Unique identifier for the task group this task belongs to
            crawler: PlaywrightCrawler instance to use for fetching

        Returns:
            None - results are saved to database and progress is sent via WebSocket
        """
        # Create a progress callback function
        progress_callback = await self._create_progress_callback(
            source_id, source_name, task_group_id
        )

        if not self._llm_pool:
            error_message = "LLM client pool not initialized"
            logger.error(error_message)
            await progress_callback("error", 0, error_message)
            return

        logger.info(
            f"Starting processing of source URL: {url} (Source: {source_name}, ID: {source_id})"
        )

        try:
            # Send initial progress update
            await progress_callback("initializing", 5, f"开始处理源: {source_name}")

            # Get category information for this source
            source_details = await self._source_repo.get_by_id_as_dict(source_id)
            if not source_details:
                await progress_callback(
                    "error", 0, f"无法获取源 ID {source_id} 的详细信息"
                )
                return

            # Extract category information
            category_id = source_details.get("category_id")
            category_name = source_details.get("category_name")

            await progress_callback("preparing", 10, "准备抓取数据...")

            # Get existing links to avoid duplicates
            exclude_links = await self._news_repo.get_all_urls()

            # Use progress callback to fetch news data
            fetch_result = await fetch_news(
                url=url,
                llm_pool=self._llm_pool,
                exclude_links=exclude_links,
                progress_callback=progress_callback,
            )

            # Process the fetched results
            if not fetch_result:
                await progress_callback("complete", 100, "完成处理，但未找到新内容")
                return

            # Add source and category information to all result items
            for result_item in fetch_result:
                result_item["source_name"] = source_name
                result_item["category_name"] = category_name
                result_item["source_id"] = source_id
                result_item["category_id"] = category_id

            print(fetch_result)
            # Update progress
            await progress_callback(
                "saving",
                95,
                f"正在保存 {len(fetch_result)} 个新闻项...",
                len(fetch_result),
            )

            # Save to database
            saved_count, skipped_count = await self._news_repo.add_batch(fetch_result)

            # Send completion notification
            await progress_callback(
                "complete",
                100,
                f"成功处理并保存了 {saved_count} 个新闻项，跳过了 {skipped_count} 个新闻项",
                saved_count,
            )

        except Exception as e:
            logger.error(f"处理 {url} 的新闻时出错: {e}", exc_info=True)
            await progress_callback("error", 0, f"处理错误: {str(e)}")
            return

    async def _create_progress_callback(
        self, source_id: int, source_name: str, task_group_id: str
    ) -> Callable:
        """
        Creates a standardized progress callback function for sending progress updates to the WebSocket.

        Args:
            source_id: The ID of the news source
            source_name: The name of the news source
            task_group_id: The ID of the task group this task belongs to

        Returns:
            A callback function that accepts step name, progress percentage, and details information
        """

        async def progress_callback(
            step: str, progress: float, details: str = "", items_count: int = 0
        ):
            """Progress callback function

            Args:
                step: The current processing step, e.g. 'crawling', 'extracting', 'analyzing', etc.
                progress: Completion percentage (0-100)
                details: Additional details information
                items_count: Number of items processed/saved
            """
            # Build a unified status update message
            update_data = {
                "source_id": source_id,
                "source_name": source_name,
                "status": "processing" if progress < 100 else "complete",
                "step": step,
                "progress": progress,
                "message": details,
            }

            # If there is a project count, add it to the update data
            if items_count > 0:
                update_data["items_saved"] = items_count

            # Send to WebSocket
            await ws_manager.send_update(task_group_id, update_data)

            # Also log to the console, maintaining a consistent log format
            logger.info(
                f"Source {source_id} ({source_name}): {step} - {progress:.1f}% - {details}"
            )

        return progress_callback

    async def stream_analysis_for_news_item(
        self, news_id: int, force: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Analyzes a specific news item and streams the results.

        Args:
            news_id: The ID of the news item to analyze
            force: If True, reanalyze even if analysis already exists

        Yields:
            Each chunk of the analysis text as it's generated

        After streaming is complete, saves the full analysis to the database
        """
        if not self._llm_pool:
            yield "Error: LLM client pool not initialized"
            return

        logger.info(f"Stream analyzing news item with ID: {news_id}")

        try:
            # Check if analysis already exists
            if not force:
                analysis = await self._news_repo.get_analysis_by_id(news_id)
                if analysis:
                    logger.info(f"Using existing analysis for news item {news_id}")
                    yield analysis
                    return

            # Get the content for analysis
            news_content = await self._news_repo.get_content_by_id(news_id)
            if not news_content:
                logger.error(f"No content found for news item {news_id}")
                yield "Error: No content available for analysis."
                return

            # Prepare prompt for the LLM
            user_prompt = f"""
                Please analyze the following news content:\n\"\"\"\n{news_content}\n\"\"\"
                **Write in the same language as the original content** (e.g., if the original content is in Chinese, the analysis should also be in Chinese). 
                """

            # Store the complete analysis text
            full_analysis = ""

            # Get the stream generator from the LLM pool
            stream = await self._llm_pool.stream_completion_content(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYZE_CONTENT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=0.7,
            )

            # Stream the analysis through the LLM
            async for chunk in stream:
                # Add to the full analysis
                full_analysis += chunk
                # Stream the chunk to the client
                yield chunk

            # Save the complete analysis to the database
            if full_analysis:
                try:
                    await self._news_repo.update_analysis(news_id, full_analysis)
                    logger.info(f"Saved analysis for news item {news_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to save analysis for news item {news_id}: {e}"
                    )
                    # No need to yield anything here, the stream has already completed

        except Exception as e:
            logger.error(f"Error in stream_analysis_for_news_item: {e}")
            yield f"Error during analysis: {str(e)}"
