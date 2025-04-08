#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News service module
Responsible for the acquisition, storage, retrieval, and management of news
"""

import json
import logging
import asyncio
import threading
from typing import List, Dict, Optional, Tuple, Callable, AsyncGenerator, Any
from datetime import datetime

from src.core.crawler import get_markdown_by_url
from src.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)
from .llm_client import LLMClient
from src.utils.token_utils import get_token_size

logger = logging.getLogger(__name__)

# Default LLM model for extraction
DEFAULT_EXTRACTION_MODEL = "deepseek-chat"


class NewsService:
    """Service class for managing news"""

    def __init__(
        self,
        news_repo: NewsRepository,
        source_repo: NewsSourceRepository,
        category_repo: NewsCategoryRepository,
        llm_client: LLMClient,
    ):
        self._news_repo = news_repo
        self._source_repo = source_repo
        self._category_repo = category_repo
        self._llm_client = llm_client

    # --- News Fetching and Processing ---

    async def fetch_news_from_sources(
        self,
        source_ids: Optional[List[int]] = None,
        on_item_saved: Optional[Callable[[Dict], None]] = None,
        on_fetch_complete: Optional[Callable[[int], None]] = None,
    ) -> int:
        """
        Fetch, extract, and save news from specified source IDs.
        If no source_ids are provided, fetch all configured news sources.

        Args:
            source_ids: List of source IDs to fetch. None means fetch all.
            on_item_saved: Callback function called after successfully saving an item to the DB.
            on_fetch_complete: Callback function called after all sources have been processed, passing the total number of successfully saved items.

        Returns:
            Total number of news entries successfully saved to the database.
        """
        sources_to_fetch = []
        if source_ids:
            all_sources = (
                self._source_repo.get_all()
            )  # Gets tuple: (id, name, url, cat_id, cat_name)
            source_map = {s[0]: s for s in all_sources}
            for src_id in source_ids:
                if src_id in source_map:
                    sources_to_fetch.append(source_map[src_id])
                else:
                    logger.warning(f"Source ID {src_id} not found in database.")
        else:
            sources_to_fetch = self._source_repo.get_all()

        if not sources_to_fetch:
            logger.warning("No valid news sources found to fetch.")
            if on_fetch_complete:
                on_fetch_complete(0)
            return 0

        # Prepare data for crawler and LLM extraction
        # Map URL to source info for easy lookup after crawling
        url_to_source_info: Dict[str, Dict[str, Any]] = {
            src[2]: {
                "id": src[0],
                "name": src[1],
                "url": src[2],
                "category_id": src[3],
                "category_name": src[4],
            }
            for src in sources_to_fetch
        }
        urls_to_crawl = list(url_to_source_info.keys())

        logger.info(f"Starting fetch process for {len(urls_to_crawl)} URLs...")

        total_saved_count = 0
        processed_url_count = 0
        all_extraction_tasks = [] # Store tasks to wait for completion

        # --- Pipeline Processing ---
        # 1. Crawl each URL in a loop
        try:
            async for crawl_result in get_markdown_by_url(urls_to_crawl):
                processed_url_count += 1
                url = crawl_result["url"]
                markdown = crawl_result.get("markdown")

                if markdown and url in url_to_source_info:
                    logger.info(f"Successfully crawled markdown for: {url}")
                    source_info = url_to_source_info[url]
                    # 2. Immediately create extraction and saving tasks for this URL
                    task = asyncio.create_task(
                        self._extract_and_save_items_sequentially(
                            url, markdown, source_info, on_item_saved
                        )
                    )
                    all_extraction_tasks.append(task)
                else:
                    logger.warning(f"Failed to get markdown or URL not found for: {url}")
                # Can add simple progress updates here, e.g. number of URLs processed

        except Exception as crawl_error:
            logger.error(f"Error during crawling phase: {crawl_error}", exc_info=True)

        logger.info(
            f"Crawling phase potentially finished (or error occurred). Processed URLs: {processed_url_count}. Waiting for extraction tasks..."
        )

        # 3. Wait for all started extraction tasks to complete and collect results
        if all_extraction_tasks:
            results = await asyncio.gather(*all_extraction_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                 # Note: result here is return value from _extract_and_save_items_sequentially (int)
                if isinstance(result, Exception):
                     logger.error(f"Error during extraction/saving task {i}: {result}", exc_info=result)
                elif isinstance(result, int):
                    total_saved_count += result # Add count of saved items from each task
                else:
                    logger.warning(f"Unexpected result type from extraction task {i}: {type(result)}")
        else:
             logger.info("No extraction tasks were started.")


        logger.info(
            f"News fetching process completed. Total items saved across all URLs: {total_saved_count}"
        )
        if on_fetch_complete:
            on_fetch_complete(total_saved_count)

        return total_saved_count
    
    def _save_item_and_callback_sync(
        self, item_data: Dict, on_item_saved: Optional[Callable[[Dict], None]]
    ) -> Optional[int]:
        """
        Synchronous helper function to save an item to the database
        and invoke the callback. Designed to be run in a background thread.

        Args:
            item_data: The dictionary containing news item data.
            on_item_saved: The callback function to call after successful save.

        Returns:
            The saved item's ID if successful, otherwise None.
        """
        thread_id = threading.get_ident() # Get current thread ID for logging
        logger.debug(f"[Thread:{thread_id}] Attempting DB save for: {item_data.get('link')}")
        saved_id = None
        try:
            # --- Database Operation ---
            saved_id = self._news_repo.add(item_data)
            # --- End Database Operation ---

            if saved_id:
                logger.info(f"[Thread:{thread_id}] Item saved (ID: {saved_id}): {item_data.get('link')}")
                # --- Callback Invocation ---
                if on_item_saved:
                    try:
                        item_data_with_id = item_data.copy()
                        item_data_with_id['id'] = saved_id # Add ID for the callback
                        # Call the callback directly from this background thread.
                        # The callback *must* handle marshalling to the GUI thread if necessary.
                        on_item_saved(item_data_with_id)
                        logger.debug(f"[Thread:{thread_id}] on_item_saved callback invoked for ID {saved_id}.")
                    except Exception as cb_err:
                        # Log error in callback but don't necessarily fail the save
                        logger.error(f"[Thread:{thread_id}] Error in on_item_saved callback for ID {saved_id}: {cb_err}", exc_info=True)
                # --- End Callback Invocation ---
                return saved_id
            else:
                # Add method might have logged duplicate/error internally
                logger.debug(f"[Thread:{thread_id}] Item not saved by repo (duplicate/error): {item_data.get('link')}")
                return None
        except Exception as db_err:
            logger.error(f"[Thread:{thread_id}] Exception during DB save for {item_data.get('link')}: {db_err}", exc_info=True)
            return None # Indicate failure
    
    async def _extract_and_save_items_sequentially(
        self,
        url: str,
        markdown: str,
        source_info: Dict[str, Any],
        on_item_saved: Optional[Callable[[Dict], None]],
    ) -> int:
        """
        Helper coroutine: Extracts items from markdown, saves each one individually,
        and calls the callback after each successful save.

        Returns:
            Number of items successfully saved for this URL.
        """
        items_saved_count = 0
        if not markdown:
            return 0

        # --- Chunking Logic ---
        token_size = get_token_size(markdown)
        MAX_MARKDOWN_TOKENS = 9216
        num_chunks = 1
        markdown_chunks = [markdown]
        if token_size > MAX_MARKDOWN_TOKENS:
            ratio = token_size // MAX_MARKDOWN_TOKENS
            num_chunks = ratio + 1
            try:
                markdown_chunks = self._get_chunks(markdown, num_chunks)
                logger.info(f"Splitting markdown for {url} into {len(markdown_chunks)} chunks ({token_size} tokens).")
            except Exception as e:
                logger.error(f"Error splitting markdown for {url}: {e}. Processing as single chunk.", exc_info=True)
                markdown_chunks = [markdown]
                num_chunks = 1

        # --- End Chunking Logic ---
        for i, chunk in enumerate(markdown_chunks):
            logger.info(f"Processing chunk {i+1}/{num_chunks} for {url} with LLM stream...")
            chunk_prompt = self._get_prompt_extract_info_from_markdown(chunk)
            stream_iterator = await self._llm_client.stream_completion_content(
                model=DEFAULT_EXTRACTION_MODEL,
                messages=[{"role": "user", "content": chunk_prompt}],
                max_tokens=8192,
            )

            if not stream_iterator:
                logger.error(f"Failed to start LLM stream for chunk {i+1}/{num_chunks} ({url}).")
                continue

            # --- Stream Parsing and Individual Saving ---
            buffer = ""
            processed_len = 0
            decoder = json.JSONDecoder()
            try:
                async for text_chunk in stream_iterator:
                    if not text_chunk: continue
                    buffer += text_chunk
                    while True:
                        buffer_trimmed = buffer[processed_len:].lstrip()
                        if not buffer_trimmed: break
                        current_start_index = len(buffer) - len(buffer_trimmed)
                        try:
                            obj, end_index_rel = decoder.raw_decode(buffer_trimmed)
                            end_index_abs = current_start_index + end_index_rel
                            processed_len = end_index_abs # Move pointer

                            # Validate and prepare data for saving
                            if isinstance(obj, dict) and obj.get("title") and obj.get("link"):
                                item_data = {
                                    "title": obj.get("title"), "link": obj.get("link"),
                                    "summary": obj.get("summary"), "published_date": obj.get("date"),
                                    "source_name": source_info["name"], "category_name": source_info["category_name"],
                                    "source_id": source_info["id"], "category_id": source_info["category_id"],
                                    "content": None, "llm_analysis": None, "embedded": False,
                                }

                                # --- Execute save and callback in background thread ---
                                try:
                                    # Use asyncio.to_thread to run the sync helper function
                                    saved_id = await asyncio.to_thread(
                                        self._save_item_and_callback_sync,
                                        item_data, # Pass current item data
                                        on_item_saved # Pass the original callback
                                    )
                                    if saved_id:
                                        items_saved_count += 1
                                        # Callback is handled within _save_item_and_callback_sync
                                except Exception as thread_exec_err:
                                    logger.error(f"Error executing save task in background thread for {url} (item: {item_data.get('link')}): {thread_exec_err}", exc_info=True)
                                # --- End Background Execution ---
                            else:
                                logger.warning(f"Skipping invalid/incomplete object from LLM stream for {url} (chunk {i+1}): {str(obj)[:100]}")

                        except json.JSONDecodeError:
                            break # Wait for more data
                        except Exception as inner_e:
                            logger.error(f"Error decoding object in stream for {url} (chunk {i+1}): {inner_e}", exc_info=True)
                            index = buffer_trimmed.find("{")
                            if index != -1: processed_len = current_start_index + index
                            else: processed_len = len(buffer)
                            break # Skip error section

            except Exception as stream_proc_err:
                 logger.error(f"Error processing LLM stream for {url} (chunk {i+1}): {stream_proc_err}", exc_info=True)
            # --- End Stream Parsing and Individual Saving ---

        logger.info(f"Finished processing all chunks for {url}. Total items saved for this URL: {items_saved_count}")
        return items_saved_count

    def _get_chunks(self, text: str, num_chunks: int) -> List[str]:
        """Splits text into roughly equal chunks based on lines."""
        lines = text.splitlines()
        if not lines:
            return []
        total_lines = len(lines)
        lines_per_chunk = max(1, total_lines // num_chunks)

        chunks = []
        for i in range(num_chunks):
            start = i * lines_per_chunk
            # For the last chunk, take all remaining lines
            end = (i + 1) * lines_per_chunk if i < num_chunks - 1 else total_lines
            chunks.append("\n".join(lines[start:end]))

        return [chunk for chunk in chunks if chunk]  # Remove empty chunks

    def _get_prompt_extract_info_from_markdown(self, markdown: str) -> str:
        """Generates the prompt for LLM extraction."""
        # (Keep the original prompt structure - it seems well-defined)
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""You are an information extraction assistant. Given a markdown-formatted text, please extract valid information according to the following strict rules:
1. Extract only valid content with links. Filter out irrelevant content such as navigation menus, login information, advertisements, feature introductions, UI elements, personal information, and any links that do not lead to substantial informational content (e.g., links to search pages, landing pages with little content, or unrelated promotional links).
2. For each valid content, extract only the following four fields:
   - title (the text title corresponding to the link, must not be empty)
   - link (the URL address of the link, must be a valid URL)
   - summary (the description or summary text associated with the link; leave empty "" if none exists)
   - date (the date when the content was published, deduced from the context or surrounding text; if no specific date can be deduced, leave it empty "". Use YYYY-MM-DD format if possible. Current date is {current_date})
3. The summary and date fields are optional; only populate them if clearly available. Title and link are mandatory.
4. Ensure the 'link' field contains a complete and valid URL (starting with http:// or https://). Resolve relative URLs if possible based on the context, otherwise skip the item.
5. The output format MUST be one valid JSON object per line. Do NOT wrap the output in a list (square brackets `[]`). Do not add commas between the JSON objects. Each line must start with `{{` and end with `}}`.

<ExampleInput>
[Windows running on smartwatches amazes netizens: This time it's true Windows on Arm](https://blog.csdn.net/csdnnews/article/details/146969048) Published on 2025-04-01. [After 25 years of coding, a veteran programmer discovers: AI assistants might still be "half-baked"!](https://blog.csdn.net/csdnnews/article/details/146967618) [A sip of alanchanchn](https://blog.csdn.net/chenwewi520feng) [Operation and maintenance monitoring](https://blog.csdn.net/chenwewi520feng/article/details/141623081) [This example collects host information...] Posted yesterday. [Login](https://example.com/login)
</ExampleInput>

<CorrectOutputFormat>
{{"title": "Windows running on smartwatches amazes netizens: This time it's true Windows on Arm", "link": "https://blog.csdn.net/csdnnews/article/details/146969048", "summary": "", "date": "2025-04-01"}}
{{"title": "After 25 years of coding, a veteran programmer discovers: AI assistants might still be \\"half-baked\\"!", "link": "https://blog.csdn.net/csdnnews/article/details/146967618", "summary": "", "date": ""}}
{{"title": "Operation and maintenance monitoring", "link": "https://blog.csdn.net/chenwewi520feng/article/details/141623081", "summary": "This example collects host information...", "date": "2025-04-04"}}
</CorrectOutputFormat>

Please start processing the following markdown content, ensuring each extracted item is a valid JSON object on its own line:
<markdown>
{markdown}
</markdown>
"""
        return prompt

    # --- News Management ---

    def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single news item by ID."""
        return self._news_repo.get_by_id(news_id)

    def get_all_news(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves all news items with pagination."""
        return self._news_repo.get_all(limit, offset)

    def delete_news(self, news_id: int) -> bool:
        """Deletes a news item."""
        # Consider deleting related embeddings as well?
        return self._news_repo.delete(news_id)

    def clear_all_news(self) -> bool:
        """Clears all news data from the database."""
        # Add warning? This is destructive.
        logger.warning("Executing clear_all_news - All news data will be removed.")
        return self._news_repo.clear_all()
        # Consider clearing ChromaDB data as well?

    # --- Category and Source Management ---

    def get_all_categories(self) -> List[Tuple[int, str]]:
        """Gets all news categories."""
        return self._category_repo.get_all()

    def get_all_categories_with_counts(self) -> List[Tuple[int, str, int]]:
        """Gets categories with source counts."""
        return self._category_repo.get_with_source_count()

    def add_category(self, name: str) -> Optional[int]:
        """Adds a new category."""
        return self._category_repo.add(name)

    def update_category(self, category_id: int, new_name: str) -> bool:
        """Updates a category name."""
        # Also update category_name in news table? Could be complex.
        # Simpler to just update the category table. UI might need refresh.
        return self._category_repo.update(category_id, new_name)

    def delete_category(self, category_id: int) -> bool:
        """Deletes a category and associated sources (due to DB cascade)."""
        logger.warning(
            f"Deleting category ID {category_id} will also delete associated news sources."
        )
        return self._category_repo.delete(category_id)

    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Gets all news sources with category names."""
        rows = self._source_repo.get_all()
        # Convert tuples to dicts for easier use
        return [
            {
                "id": r[0],
                "name": r[1],
                "url": r[2],
                "category_id": r[3],
                "category_name": r[4],
            }
            for r in rows
        ]

    def get_sources_by_category_id(self, category_id: int) -> List[Dict[str, Any]]:
        """Gets sources for a specific category."""
        rows = self._source_repo.get_by_category(category_id)
        return [{"id": r[0], "name": r[1], "url": r[2]} for r in rows]

    def add_source(self, name: str, url: str, category_name: str) -> Optional[int]:
        """Adds a news source. Creates category if it doesn't exist."""
        # Find or create category
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(
                    f"Failed to add or find category '{category_name}' when adding source."
                )
                return None
        else:
            category_id = category[0]

        return self._source_repo.add(name, url, category_id)

    def update_source(
        self, source_id: int, name: str, url: str, category_name: str
    ) -> bool:
        """Updates a news source."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(
                    f"Failed to add or find category '{category_name}' when updating source."
                )
                return False
        else:
            category_id = category[0]

        return self._source_repo.update(source_id, name, url, category_id)

    def delete_source(self, source_id: int) -> bool:
        """Deletes a news source."""
        return self._source_repo.delete(source_id)
