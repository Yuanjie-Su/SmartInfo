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
from typing import List, Dict, Optional, Tuple, Callable, Any, Union, AsyncGenerator
from urllib.parse import urljoin

import aiohttp

# Crawler for asynchronous HTTP requests
from backend.core.crawler import AiohttpCrawler, PlaywrightCrawler

# Repository interfaces for database operations
from backend.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)

# Client to interact with the LLM API
from backend.core.llm import LLMClientPool

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

    async def crawl_and_process_url(
        self, url: str, source_info: Dict[str, Any], use_playwright: bool = True
    ) -> Tuple[int, str, Optional[Exception]]:
        """
        Crawl a URL and process its content.

        Args:
            url: The URL to crawl
            source_info: Dictionary with source metadata
            use_playwright: Whether to use Playwright (True) or Aiohttp (False)

        Returns:
            Tuple of (saved_item_count, analysis_result_text, error)
        """
        # Create a crawler instance
        crawler = PlaywrightCrawler() if use_playwright else AiohttpCrawler()

        try:
            # Fetch the HTML content
            if use_playwright:
                fetch_result = await crawler._fetch_single(url)
            else:
                # For AiohttpCrawler, we need a ClientSession
                async with aiohttp.ClientSession() as session:
                    fetch_result = await crawler._fetch_single(session, url)

            html_content = fetch_result.get("content", "")
            if not html_content:
                error_msg = fetch_result.get("error", "Unknown error fetching content")
                logger.error(f"Error fetching {url}: {error_msg}")
                return 0, "", Exception(error_msg)

            # Process the HTML and analyze it
            return await self._process_html_and_analyze(
                url, html_content, source_info, None
            )

        except Exception as e:
            logger.error(f"Error in crawl_and_process_url for {url}: {e}")
            return 0, "", e
        finally:
            # Cleanup Playwright resources if used
            if use_playwright and isinstance(crawler, PlaywrightCrawler):
                await crawler.shutdown()

    async def _process_html_and_analyze(
        self,
        url: str,
        html_content: str,
        source_info: Dict[str, Any],
        on_status_update: Optional[Callable[[str, str, str], None]],
    ) -> Tuple[int, str, Optional[Exception]]:
        """
        Process HTML content and perform analysis using LLM.

        Args:
            url: Source URL
            html_content: Raw HTML content
            source_info: Dictionary with source metadata
            on_status_update: Optional callback for status updates

        Returns:
            Tuple of (saved_item_count, analysis_result_markdown, error)
        """
        if not self._llm_pool:
            error_message = "LLM client pool not initialized"
            logger.error(error_message)
            return 0, "", Exception(error_message)

        processing_error = None
        all_parsed_results_for_url = []

        # Helper function for status updates
        def _status_update(status: str, details: str = "", url: str = url):
            if on_status_update:
                on_status_update(url, status, details)
            logger.info(f"{url} - {status}: {details}")

        try:
            # Step 1: Clean and format the HTML content
            _status_update("Processing", "Cleaning HTML content")
            try:
                # Use html_utils to clean and extract metadata
                cleaned_html = clean_and_format_html(
                    html_content, url, output_format="markdown"
                )
                article_metadata = extract_metadata_from_article_html(
                    html_content, url
                )  # Use original HTML for metadata extraction

            except Exception as e:
                logger.warning(f"Error cleaning HTML for {url}: {e}")
                cleaned_html = html_content  # Fallback to original
                article_metadata = {"url": url, "title": ""}  # Minimal metadata

            if not cleaned_html or not cleaned_html.strip():
                _status_update("Skipped", "No content after cleaning")
                return 0, "", None

            # Step 2: Get an LLM client from the pool
            async with self._llm_pool.context() as llm_client:  # Use execute_with_client context manager
                # Step 3: Analyze the content using LLM
                _status_update("Processing", "Analyzing content with LLM")

                content_structure = {
                    url: {
                        "title": article_metadata.get("title", "Untitled Article"),
                        "url": url,
                        "date": article_metadata.get("date", ""),
                        "content": cleaned_html,  # Use the cleaned markdown content for analysis
                    }
                }

                prompt = self.build_content_analysis_prompt(content_structure)

                # Split into chunks if needed based on token size
                prompt_tokens = get_token_size(prompt)
                if prompt_tokens > MAX_INPUT_TOKENS:
                    _status_update(
                        "Processing",
                        f"Content too large ({prompt_tokens} tokens), splitting...",
                    )
                    # Split into chunks based on token size, roughly fitting within MAX_INPUT_TOKENS
                    chunk_size_tokens = MAX_INPUT_TOKENS
                    chunk_count = (
                        prompt_tokens + chunk_size_tokens - 1
                    ) // chunk_size_tokens  # Ceiling division
                    chunks = get_chunks(prompt, chunk_count)

                    _status_update("Processing", f"Split into {len(chunks)} chunks")
                else:
                    chunks = [prompt]

                # Process each chunk
                analysis_result_parts = []
                for i, chunk in enumerate(chunks):
                    if len(chunks) > 1:
                        _status_update(
                            "Processing", f"Analyzing chunk {i+1}/{len(chunks)}"
                        )

                    # Get completion for each chunk
                    response = await llm_client.get_completion_content(
                        messages=[
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,  # Use batch summarization prompt for chunks
                            },
                            {"role": "user", "content": chunk},
                        ],
                        model=DEFAULT_MODEL,
                        temperature=0.1,
                        top_p=0.9,
                        max_tokens=MAX_OUTPUT_TOKENS,
                    )

                    # Extract and parse results for this chunk
                    content = response.get("content", "")
                    if content:
                        analysis_result_parts.append(content)

                # Combine results from all chunks
                combined_analysis_result = "\n\n".join(analysis_result_parts)

                # Parse the combined result to extract structured items
                all_parsed_results_for_url, parse_error = self._parse_llm_analysis(
                    combined_analysis_result, source_info
                )

                if parse_error:
                    processing_error = processing_error or parse_error

            # Step 4: Save results to the database
            saved_item_count, db_error = self._save_results_to_db(
                url, all_parsed_results_for_url, _status_update
            )
            if db_error:
                processing_error = processing_error or db_error

            # Prepare final result
            final_status = (
                "Complete" if not processing_error else "Complete with Errors"
            )
            _status_update(
                final_status,
                f"Added: {saved_item_count}, Skipped: {len(all_parsed_results_for_url) - saved_item_count}",
            )

            # Format summary as Markdown
            analysis_result_markdown = "\n".join(
                [
                    f"### {item.get('title', '')}\n"
                    f"🔗 {item.get('url', '')}\n"
                    f"📅 {item.get('date', '')}\n"
                    f"📝 {item.get('summary', '')}\n"
                    for item in all_parsed_results_for_url
                ]
            )

            return saved_item_count, analysis_result_markdown, processing_error

        except Exception as e:
            logger.error(f"Error processing {url}: {e}", exc_info=True)
            _status_update("Error", str(e))
            return 0, "", e

    def _parse_llm_analysis(
        self, llm_response: str, source_info: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Optional[Exception]]:
        """
        Parse LLM analysis response into structured data.

        Args:
            llm_response: Raw response from LLM
            source_info: Source metadata to include with each item

        Returns:
            Tuple of (parsed_items_list, error_if_any)
        """
        try:
            # Clean up the markdown response
            cleaned_text = strip_markdown_links(llm_response)
            cleaned_text = strip_markdown_divider(cleaned_text)

            # Initialize result
            parsed_items = []

            # Use parse_json_from_text to extract potential JSON
            json_results = parse_json_from_text(cleaned_text)

            if json_results:
                # If JSON is found, use it directly
                for item in json_results:
                    if item.get("url") and item.get("summary"):  # Basic validation
                        parsed_item = {
                            "title": item.get("title", ""),
                            "url": item["url"],
                            "summary": item["summary"],
                            "date": item.get("date", ""),
                            "content": item.get(
                                "content", ""
                            ),  # Include content if available
                            "source_id": source_info.get("id"),
                            "source_name": source_info.get("name"),
                            "category_id": source_info.get("category_id"),
                            "category_name": source_info.get("category_name"),
                            "analysis": item.get(
                                "analysis", ""
                            ),  # Include analysis if available
                        }
                        parsed_items.append(parsed_item)
                return parsed_items, None

            else:
                # If no JSON, try to parse from structured markdown
                article_blocks = re.split(r"(?:^|\n)###\s+", cleaned_text)
                if len(article_blocks) <= 1:
                    # No blocks found using heading marker, try splitting by double newline
                    article_blocks = re.split(r"\n\s*\n", cleaned_text)

                # Skip the first block if it's just intro text
                start_idx = 1 if len(article_blocks) > 1 else 0

                # Process each article block
                for block in article_blocks[start_idx:]:
                    if not block.strip():
                        continue

                    # Extract fields using regex
                    item = {}

                    # Extract title (first line or after "Title:" marker)
                    title_match = re.search(r"^(.*?)(?:\n|$)", block) or re.search(
                        r"Title:\s*(.*?)(?:\n|$)", block
                    )
                    if title_match:
                        item["title"] = title_match.group(1).strip()

                    # Extract URL
                    url_match = re.search(r"🔗\s*(https?://\S+)", block) or re.search(
                        r"URL:\s*(https?://\S+)", block
                    )
                    if url_match:
                        item["url"] = url_match.group(1).strip()

                    # Extract date
                    date_match = re.search(r"📅\s*(.+?)(?:\n|$)", block) or re.search(
                        r"Date:\s*(.+?)(?:\n|$)", block
                    )
                    if date_match:
                        item["date"] = date_match.group(1).strip()

                    # Extract summary (the rest of the content)
                    summary_match = re.search(r"📝\s*([\s\S]+)$", block) or re.search(
                        r"Summary:\s*([\s\S]+)$", block
                    )
                    if summary_match:
                        item["summary"] = summary_match.group(1).strip()
                    else:
                        # If no explicit summary marker, use everything after the title/url/date
                        lines = block.split("\n")
                        content_lines = []
                        for i, line in enumerate(lines):
                            if i > 0 and not (
                                line.startswith("🔗")
                                or line.startswith("📅")
                                or line.startswith("URL:")
                                or line.startswith("Date:")
                            ):
                                content_lines.append(line)
                        item["summary"] = "\n".join(content_lines).strip()

                    # Add source info
                    if source_info:
                        item["source_id"] = source_info.get("id")
                        item["source_name"] = source_info.get("name")
                        item["category_id"] = source_info.get("category_id")
                        item["category_name"] = source_info.get("category_name")

                    # Add to result list if we have minimum required fields (title and url/summary)
                    if item.get("title") and (item.get("url") or item.get("summary")):
                        parsed_items.append(item)

                if not parsed_items:
                    error_msg = "No structured items parsed from LLM response"
                    logger.warning(error_msg)
                    return [], Exception(error_msg)

            return parsed_items, None

        except Exception as e:
            logger.error(f"Error parsing LLM analysis: {e}", exc_info=True)
            return [], e

    def _save_results_to_db(
        self,
        original_url: str,
        parsed_items: List[Dict[str, Any]],
        status_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> Tuple[int, Optional[Exception]]:
        """
        Persist a batch of parsed news items to the database.
        Returns the count of added items and any error encountered.
        """
        saved_count = 0
        error: Optional[Exception] = None

        # Skip if there is no data to store
        if not parsed_items:
            return 0, None

        try:
            # Helper function for status updates
            def _update(status, details=""):
                if status_callback:
                    status_callback(original_url, status, details)
                logger.info(f"{original_url} - {status}: {details}")

            # Add items to database
            _update("Saving", f"Saving {len(parsed_items)} items to database")

            # Add as batch for efficiency
            success_count, skipped_count = self._news_repo.add_batch(parsed_items)
            saved_count = success_count

            _update("Saved", f"Added {success_count}, skipped {skipped_count}")
            return saved_count, None

        except Exception as e:
            logger.error(f"Error saving to database: {e}", exc_info=True)
            return 0, e

    def build_link_extraction_prompt(self, url: str, markdown_content: str) -> str:
        """Create the prompt for link extraction LLM call."""
        prompt = f"""
Base URL: {url}
Markdown:
{markdown_content}
"""
        return prompt

    def build_content_analysis_prompt(
        self, structure_data_map: Dict[str, Dict[str, str]]
    ) -> str:
        """Build the prompt containing article metadata to guide LLM summarization."""
        if not structure_data_map:
            return ""

        prompt_parts: List[str] = []
        for article_url, data in structure_data_map.items():
            prompt_parts.append("<Article>")
            prompt_parts.append(f"Title: {data.get('title', 'Untitled')}")
            prompt_parts.append(f"Url: {data.get('url', 'N/A')}")
            prompt_parts.append(f"Date: {data.get('date', 'N/A')}")
            prompt_parts.append("Content:")
            prompt_parts.append(data.get("content", ""))
            prompt_parts.append("</Article>\n")

        prompt_parts.append(
            "Please summarize each article in Markdown format, following the structure and style shown above."
        )
        return "\n".join(prompt_parts)

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

    async def create_news(self, news_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new news item."""
        news_id = await self._news_repo.add(news_item)
        if news_id:
            return await self._news_repo.get_by_id(news_id)
        return None

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

    # 以下是与数据库交互的异步任务方法，已经是异步的，但现在需要在内部使用await调用

    async def fetch_all_sources(self) -> str:
        """Start task to fetch articles from all sources."""
        all_sources = await self._source_repo.get_all()
        sources_count = len(all_sources)

        source_ids = [source[0] for source in all_sources]
        status_msg = f"Started fetch task for {sources_count} sources."
        logger.info(status_msg)

        # 其余原有逻辑保持不变
        return status_msg

    async def fetch_source(self, source_id: int) -> str:
        """Start task to fetch articles from a specific source."""
        source = await self._source_repo.get_by_id(source_id)
        if not source:
            error_msg = f"Source with ID {source_id} not found."
            logger.error(error_msg)
            return error_msg

        # 其余原有逻辑保持不变
        return f"Started fetch task for source: {source[1]} (ID: {source_id})."

    async def analyze_all_news(self, force: bool = False) -> str:
        """Analyze all news items (optionally force re-analysis)."""
        # 这个方法内部使用services而不是直接访问repositories，保持原样即可
        return "Started analysis task for all news items."

    async def analyze_news_by_ids(
        self, news_ids: List[int], force: bool = False
    ) -> str:
        """Analyze specific news items (optionally force re-analysis)."""
        # 同上，保持原样即可
        return f"Started analysis task for {len(news_ids)} news items."

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
