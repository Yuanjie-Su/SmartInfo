#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News service module
Responsible for the acquisition, storage, retrieval, and management of news
"""

import json
import logging
import asyncio
import re
import threading
# Added Callable for the new callback type
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
DEFAULT_EXTRACTION_MODEL = "deepseek-v3-250324"
MAX_MARKDOWN_TOKENS = 20480 # 20k
MAX_OUTPUT_TOKENS = 16384 # 16k
# MAX_CONTEXT_TOKENS = 131072 # 128k


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
        on_url_status_update: Optional[Callable[[str, str, str], None]] = None,
    ) -> int:
        """
        Fetch, extract, and save news from specified source IDs using non-streaming LLM.
        Reports progress per URL via on_url_status_update callback.

        Args:
            source_ids: List of source IDs to fetch. None means fetch all.
            on_url_status_update: Callback receiving (url, status, details).

        Returns:
            Total number of news entries successfully saved to the database.
        """
        sources_to_fetch = []
        if source_ids:
            all_sources = self._source_repo.get_all()
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
            return 0

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

        total_saved_count = 0
        processed_url_count = 0
        all_extraction_tasks = []

        # Report initial status (optional, UI can handle this)
        # if on_url_status_update:
        #     for url in urls_to_crawl:
        #         on_url_status_update(url, "Pending", "")

        logger.info(f"Crawling {len(urls_to_crawl)} sources...")

        try:
            async for crawl_result in get_markdown_by_url(urls_to_crawl):
                processed_url_count += 1
                url = crawl_result["url"]
                markdown = crawl_result.get("markdown")
                source_info = url_to_source_info.get(url)

                if not source_info:
                     logger.warning(f"Received crawl result for unknown URL: {url}")
                     continue

                if on_url_status_update:
                    status = "Crawled - Success" if markdown else "Crawled - Failed (No Markdown)"
                    on_url_status_update(url, status, "")

                if markdown:
                    logger.info(f"Successfully crawled markdown for: {url}")
                    task = asyncio.create_task(
                        self._extract_and_save_items_sequentially(
                            url,
                            markdown,
                            source_info,
                            on_url_status_update, # Pass new callback
                        )
                    )
                    all_extraction_tasks.append(task)
                else:
                    logger.warning(f"Failed to get markdown for: {url}")
                    # Report error via callback if desired, or just log
                    if on_url_status_update:
                         on_url_status_update(url, "Error", "Failed to crawl markdown")


        except Exception as crawl_error:
            logger.error(f"Error during crawling phase: {crawl_error}", exc_info=True)
            # Report error for all pending URLs? Difficult to track which failed here.

        logger.info(f"Crawling phase finished. Processed URLs: {processed_url_count}. Waiting for extraction tasks...")

        if all_extraction_tasks:
            results = await asyncio.gather(*all_extraction_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                task_url = f"Task {i}" # Placeholder
                saved_count = 0
                task_exception = None

                if isinstance(result, Exception):
                    task_exception = result
                    # Need to associate exception back to a URL if possible (tricky here)
                    # Maybe the task itself should catch and return (url, error)?
                elif isinstance(result, tuple) and len(result) == 2:
                    task_url, saved_count_or_error = result
                    if isinstance(saved_count_or_error, int):
                        saved_count = saved_count_or_error
                    else:
                        task_exception = saved_count_or_error # Assume error obj/string
                        # Report error for this specific URL
                        if on_url_status_update:
                            on_url_status_update(task_url, "Error", str(task_exception))

                if task_exception:
                    logger.error(f"Error during extraction/saving task for {task_url}: {task_exception}", exc_info=isinstance(task_exception, Exception))
                else:
                    total_saved_count += saved_count

        else:
             logger.info("No extraction tasks were started.")

        logger.info(f"News fetching process completed. Total items saved across all sources: {total_saved_count}")
        return total_saved_count

    async def _extract_and_save_items_sequentially(
        self,
        url: str,
        markdown: str,
        source_info: Dict[str, Any],
        on_url_status_update: Optional[Callable[[str, str, str], None]],
    ) -> Tuple[str, Any]: # Return URL and (count or error)
        """
        Helper coroutine: Extracts items from markdown using non-streaming LLM,
        collects them, and saves them in a single batch. Reports status updates.

        Args:
            url: The source URL being processed.
            markdown: The crawled markdown content.
            source_info: Dictionary containing info about the source.
            on_url_status_update: Callback for status updates.

        Returns:
            Tuple of (URL, Number of saved items OR Error object/string).
        """
        items_to_save_batch: List[Dict[str, Any]] = []
        total_saved_for_url = 0
        total_skipped_for_url = 0

        try: # Wrap the whole process for better error reporting per URL
            if not markdown:
                if on_url_status_update: on_url_status_update(url, "Skipped", "No markdown content")
                return url, 0 # Return 0 saved

            if on_url_status_update:
                on_url_status_update(url, "Processing", "Checking token size")

            # --- Chunking Logic (Still relevant for large markdown) ---
            token_size = get_token_size(markdown)
            markdown_chunks = [markdown]
            num_chunks = 1

            if token_size > MAX_MARKDOWN_TOKENS:
                num_chunks = (token_size // MAX_MARKDOWN_TOKENS) + 1
                try:
                    markdown_chunks = self._get_chunks(markdown, num_chunks)
                    log_msg = f"Splitting markdown for {url} into {len(markdown_chunks)} chunks ({token_size} tokens)."
                    logger.info(log_msg)
                    if on_url_status_update: on_url_status_update(url, "Processing", f"Splitting into {len(markdown_chunks)} chunks")
                except Exception as e:
                    log_msg = f"Error splitting markdown for {url}: {e}. Processing as single chunk."
                    logger.error(log_msg, exc_info=True)
                    markdown_chunks = [markdown]
                    num_chunks = 1
                    if on_url_status_update: on_url_status_update(url, "Processing", "Split failed, using single chunk")
            # --- End Chunking Logic ---

            # --- Process Chunks ---
            for i, chunk in enumerate(markdown_chunks):
                if not chunk or not chunk.strip():
                    logger.debug(f"Skipping empty chunk {i+1}/{num_chunks} for {url}")
                    continue

                chunk_status_prefix = f"Chunk {i+1}/{num_chunks}"
                if on_url_status_update: on_url_status_update(url, "Extracting (LLM)", f"{chunk_status_prefix} Sending request...")
                logger.info(f"Processing chunk {i+1}/{num_chunks} for {url} with non-streaming LLM...")

                chunk_prompt = self._get_prompt_extract_info_from_markdown(chunk)

                # --- Call Non-Streaming LLM ---
                llm_result = await self._llm_client.get_completion_content(
                    model=DEFAULT_EXTRACTION_MODEL,
                    messages=[{"role": "user", "content": chunk_prompt}],
                    max_tokens=MAX_OUTPUT_TOKENS, # Might need adjustment based on expected output size
                    temperature=0.1
                )
                # --- End LLM Call ---

                if llm_result:
                    logger.info(f"LLM extraction successful for chunk {i+1}/{num_chunks} ({url}).")
                    if on_url_status_update: on_url_status_update(url, "Extracting (LLM)", f"{chunk_status_prefix} Received response")
                    # Process and save the extracted items
                    try:
                        print(llm_result)
                        items_extracted = json.loads(llm_result)
                        if isinstance(items_extracted, list) and items_extracted and isinstance(items_extracted[0], dict):
                            # Enrich items with source information before saving
                            enriched_items = []
                            for item in items_extracted:
                                if isinstance(item, dict) and item.get('link') and item.get('title'): # Basic validation
                                    item['source_id'] = source_info.get('id')
                                    item['source_name'] = source_info.get('name')
                                    item['category_id'] = source_info.get('category_id')
                                    item['category_name'] = source_info.get('category_name')
                                    enriched_items.append(item)
                                else:
                                    logger.warning(f"Skipping invalid item structure in LLM result for {url}: {item}")

                            if enriched_items:
                                logger.info(f"Saving {len(enriched_items)} enriched items from LLM result for {url}...")
                                success_count, skipped_count = self._news_repo.add_batch(enriched_items)
                                total_saved_for_url += success_count
                                total_skipped_for_url += skipped_count
                                logger.info(f"Saved: {success_count}, Skipped (duplicates): {skipped_count} for chunk {i+1}/{num_chunks} ({url}).")
                                if on_url_status_update: on_url_status_update(url, "Saving", f"{chunk_status_prefix} Saved {success_count}, Skipped {skipped_count}")
                            else:
                                logger.info(f"No valid items to save after enrichment for chunk {i+1}/{num_chunks} ({url}).")

                        elif isinstance(items_extracted, list) and not items_extracted:
                             logger.info(f"LLM returned an empty list for chunk {i+1}/{num_chunks} ({url}).")
                        else:
                            logger.warning(f"Invalid LLM result format for {url}. Expected non-empty list of dictionaries, got: {type(items_extracted)}")
                            if on_url_status_update: on_url_status_update(url, "Error", "Invalid result format")
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing LLM JSON result for {url}: {e}", exc_info=True)
                        if on_url_status_update: on_url_status_update(url, "Error", f"JSON Parsing Failed: {e}")
                    except Exception as e: # Catch other potential errors during enrichment/saving
                        logger.error(f"Error processing/saving LLM result for {url}: {e}", exc_info=True)
                        if on_url_status_update: on_url_status_update(url, "Error", f"Processing Failed: {e}")
                else:
                    logger.warning(f"LLM returned empty result for chunk {i+1}/{num_chunks} ({url}).")
                    if on_url_status_update: on_url_status_update(url, "Extracting (LLM)", f"{chunk_status_prefix} Failed (No response)")

        except Exception as e:
             logger.error(f"Critical error processing URL {url}: {e}", exc_info=True)
             if on_url_status_update: on_url_status_update(url, "Error", f"Processing Failed: {e}")
             return url, e # Return error


    def _get_chunks(self, text: str, num_chunks: int) -> List[str]:
        """Splits text into roughly equal chunks based on lines."""
        lines = text.splitlines()
        if not lines:
            return []
        total_lines = len(lines)
        # Ensure lines_per_chunk is at least 1
        lines_per_chunk = max(1, total_lines // num_chunks)

        chunks = []
        start_line = 0
        for i in range(num_chunks):
            # Calculate end line, ensuring the last chunk takes all remaining lines
            end_line = start_line + lines_per_chunk if i < num_chunks - 1 else total_lines
            # Ensure end_line doesn't exceed total_lines (can happen with integer division)
            end_line = min(end_line, total_lines)
            # Add chunk if start_line is less than end_line
            if start_line < end_line:
                chunks.append("\n".join(lines[start_line:end_line]))
            # Update start_line for the next chunk
            start_line = end_line
            # Break if we've processed all lines
            if start_line >= total_lines:
                break

        return [chunk for chunk in chunks if chunk and chunk.strip()] # Remove empty chunks


    def _get_prompt_extract_info_from_markdown(self, markdown: str) -> str:
        """Generates the prompt for LLM extraction."""
        # (Keep the original prompt structure)
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""You are an information extraction assistant. Given a markdown-formatted text, please extract valid information according to the following strict rules:
1. Extract only valid content with links. Filter out irrelevant content such as navigation menus, login information, advertisements, feature introductions, UI elements, personal information, and any links that do not lead to substantial informational content (e.g., links to search pages, landing pages with little content, or unrelated promotional links).
2. For each valid content, extract only the following four fields:
   - "title": the text title corresponding to the link, must not be empty
   - "link": the URL address of the link, must be a valid URL starting with http:// or https://
   - "summary": the description or summary text associated with the link. If no summary exists, set it to "". If the summary exists and exceeds 100 words, summarize and reduce it to approximately 80 words. If the summary is already less than 80 words, leave it as-is.
   - "date": the date when the content was published, deduced from the context or surrounding text. If no specific date can be deduced, set it to "". Use YYYY-MM-DD format if possible. Current date is {current_date}
3. The "summary" and "date" fields are optional; only populate them if clearly available. The "title" and "link" fields are mandatory.
4. Ensure the "link" field contains a complete and valid URL. Resolve relative URLs if possible based on the context; otherwise skip the item.
5. The output MUST be a valid JSON array beginning with [ and ending with ]. Each item must be a JSON object. **Do not include markdown code block syntax like json``` and ```.**

<ExampleInput>
[Windows running on smartwatches amazes netizens: This time it's true Windows on Arm](https://blog.csdn.net/csdnnews/article/details/146969048) Published on 2025-04-01. [After 25 years of coding, a veteran programmer discovers: AI assistants might still be "half-baked"!](https://blog.csdn.net/csdnnews/article/details/146967618) [A sip of alanchanchn](https://blog.csdn.net/chenwewi520feng) [Operation and maintenance monitoring](https://blog.csdn.net/chenwewi520feng/article/details/141623081) [This example collects host information...] Posted yesterday. [Login](https://example.com/login)
</ExampleInput>

<CorrectOutputFormat>
[
  {{
    "title": "Windows running on smartwatches amazes netizens: This time it's true Windows on Arm",
    "link": "https://blog.csdn.net/csdnnews/article/details/146969048",
    "summary": "",
    "date": "2025-04-01"
  }},
  {{
    "title": "After 25 years of coding, a veteran programmer discovers: AI assistants might still be \"half-baked\"!",
    "link": "https://blog.csdn.net/csdnnews/article/details/146967618",
    "summary": "",
    "date": ""
  }},
  {{
    "title": "Operation and maintenance monitoring",
    "link": "https://blog.csdn.net/chenwewi520feng/article/details/141623081",
    "summary": "This example collects host information...",
    "date": "2025-04-07"
  }}
]
</CorrectOutputFormat>

Please start processing the following markdown content, ensuring the final output is a valid JSON array:
<markdown>
{markdown}
</markdown>
"""

        return prompt

    # --- News Management --- (Keep remaining methods as they are)
    # get_news_by_id, get_all_news, delete_news, clear_all_news
    # get_all_categories, get_all_categories_with_counts, add_category, etc.
    # get_all_sources, get_sources_by_category_id, add_source, etc.
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
        # Consider coordinating with QA service to clear ChromaDB data as well
        return self._news_repo.clear_all()


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
        return [
            {
                "id": r[0], "name": r[1], "url": r[2],
                "category_id": r[3], "category_name": r[4],
            }
            for r in rows
        ]

    def get_sources_by_category_id(self, category_id: int) -> List[Dict[str, Any]]:
        """Gets sources for a specific category."""
        rows = self._source_repo.get_by_category(category_id)
        return [{"id": r[0], "name": r[1], "url": r[2]} for r in rows]

    def add_source(self, name: str, url: str, category_name: str) -> Optional[int]:
        """Adds a news source. Creates category if it doesn't exist."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(f"Failed to add/find category '{category_name}'")
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
                logger.error(f"Failed to add/find category '{category_name}'")
                return False
        else:
            category_id = category[0]
        return self._source_repo.update(source_id, name, url, category_id)

    def delete_source(self, source_id: int) -> bool:
        """Deletes a news source."""
        return self._source_repo.delete(source_id)