#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News service module
Responsible for the acquisition, storage, retrieval, and management of news
"""

import json
import logging
import asyncio
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
        on_item_extracted: Optional[Callable[[Dict], None]] = None,
        on_fetch_complete: Optional[Callable[[int], None]] = None,
    ) -> int:
        """
        Fetch, extract, and save news from specified source IDs.
        If no source_ids are provided, fetch all configured news sources.

        Args:
            source_ids: List of source IDs to fetch. None means fetch all.
            on_item_extracted: Callback function called after successfully extracting and attempting to save an item.
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

        # 1. Crawl to get Markdown content for all URLs
        # Use a dictionary to store markdown results keyed by URL
        markdown_results: Dict[str, str] = {}
        try:
            async for crawl_result in get_markdown_by_url(urls_to_crawl):
                processed_url_count += 1
                if crawl_result.get("markdown"):
                    markdown_results[crawl_result["url"]] = crawl_result["markdown"]
                    logger.info(
                        f"Successfully crawled markdown for: {crawl_result['url']}"
                    )
                else:
                    logger.warning(f"Failed to get markdown for: {crawl_result['url']}")
                # Optionally report progress here if needed (e.g., update UI)

        except Exception as crawl_error:
            logger.error(f"Error during crawling phase: {crawl_error}", exc_info=True)
            # Decide how to handle crawl errors - stop or continue? Let's continue with what we have.

        logger.info(
            f"Crawling phase complete. Got markdown for {len(markdown_results)} out of {processed_url_count} processed URLs."
        )

        # 2. Process each markdown with LLM for extraction
        extraction_tasks = []
        for url, markdown_content in markdown_results.items():
            if url in url_to_source_info:
                source_info = url_to_source_info[url]
                # Create an async task for each extraction
                task = self._extract_and_save_from_markdown(
                    url, markdown_content, source_info, on_item_extracted
                )
                extraction_tasks.append(task)
            else:
                logger.warning(
                    f"URL {url} from crawl result not found in initial source list. Skipping extraction."
                )

        # Run all extraction tasks concurrently
        if extraction_tasks:
            logger.info(
                f"Starting LLM extraction for {len(extraction_tasks)} sources..."
            )
            results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Process results (count successes, log errors)
            for i, result in enumerate(results):
                original_url = list(markdown_results.keys())[
                    i
                ]  # Get URL based on task order
                if isinstance(result, Exception):
                    logger.error(
                        f"Error during extraction/saving for URL {original_url}: {result}",
                        exc_info=result,
                    )
                elif isinstance(result, int):
                    total_saved_count += (
                        result  # Result is the count of saved items for this URL
                    )
                else:
                    logger.warning(
                        f"Unexpected result type from extraction task for URL {original_url}: {type(result)}"
                    )
        else:
            logger.info("No markdown content available for LLM extraction.")

        logger.info(
            f"News fetching process completed. Total items saved: {total_saved_count}"
        )
        if on_fetch_complete:
            on_fetch_complete(total_saved_count)

        return total_saved_count

    async def _extract_and_save_from_markdown(
        self,
        url: str,
        markdown: str,
        source_info: Dict[str, Any],
        on_item_extracted: Optional[Callable[[Dict], None]],
    ) -> int:
        """
        Helper coroutine to extract info from markdown using LLM and save results.

        Returns:
            Number of items saved for this specific URL.
        """
        if not markdown:
            return 0

        # prompt = self._get_prompt_extract_info_from_markdown(markdown)
        token_size = get_token_size(markdown)
        # Simplified chunking logic (adjust threshold as needed)
        # Max tokens for deepseek-chat is high, but let's be conservative
        # ~10k tokens for context, prompt itself takes some space.
        # Let's target chunks under ~9k tokens for the markdown part.
        # Assuming prompt overhead is ~300 tokens.
        MAX_MARKDOWN_TOKENS = 9216
        num_chunks = 1
        markdown_chunks = [markdown]

        if token_size > MAX_MARKDOWN_TOKENS:
            ratio = token_size // MAX_MARKDOWN_TOKENS
            num_chunks = ratio + 1
            try:
                markdown_chunks = self._get_chunks(markdown, num_chunks)
                logger.info(
                    f"Splitting markdown for {url} into {len(markdown_chunks)} chunks ({token_size} tokens)."
                )
            except Exception as e:
                logger.error(
                    f"Error splitting markdown for {url}: {e}. Processing as single chunk.",
                    exc_info=True,
                )
                markdown_chunks = [markdown]
                num_chunks = 1

        chunk_saved_count = 0
        processed_items = []  # Store items extracted from all chunks of this URL

        for i, chunk in enumerate(markdown_chunks):
            logger.info(
                f"Processing chunk {i+1}/{num_chunks} for {url} with LLM stream..."
            )
            chunk_prompt = self._get_prompt_extract_info_from_markdown(chunk)
            # Use the injected LLM client
            stream_iterator = await self._llm_client.stream_completion_content(
                model=DEFAULT_EXTRACTION_MODEL,
                messages=[{"role": "user", "content": chunk_prompt}],
                max_tokens=8192,
            )

            if not stream_iterator:
                logger.error(
                    f"Failed to start LLM stream for chunk {i+1}/{num_chunks} ({url})."
                )
                continue  # Skip to next chunk or finish if last chunk

            # Process the stream using robust JSON parsing
            items_from_chunk = await self._parse_json_stream(
                stream_iterator, url, i + 1
            )
            processed_items.extend(items_from_chunk)
            logger.info(
                f"Extracted {len(items_from_chunk)} items from chunk {i+1}/{num_chunks} for {url}."
            )

        # After processing all chunks, save the collected items in batch
        if processed_items:
            logger.info(
                f"Attempting to save {len(processed_items)} extracted items for {url}..."
            )
            items_to_save = []
            for item in processed_items:
                # Add source and category info before saving
                item_data = {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "summary": item.get("summary"),
                    "published_date": item.get("date"),
                    # Add source/category info from the source_info dict
                    "source_name": source_info["name"],
                    "category_name": source_info["category_name"],
                    "source_id": source_info["id"],
                    "category_id": source_info["category_id"],
                    "content": None,
                    "llm_analysis": None,
                    "embedded": False,
                }
                items_to_save.append(item_data)

                # Trigger callback for each potentially savable item (before batch save)
                if on_item_extracted:
                    try:
                        on_item_extracted(item_data.copy())  # Send a copy
                    except Exception as cb_err:
                        logger.error(
                            f"Error in on_item_extracted callback for {url}: {cb_err}",
                            exc_info=True,
                        )

            # Batch save using the repository
            saved_count, skipped_count = self._news_repo.add_batch(items_to_save)
            chunk_saved_count = saved_count  # Total saved for this URL
            logger.info(
                f"Saved {saved_count} new items, skipped {skipped_count} for {url}."
            )

        return chunk_saved_count

    async def _parse_json_stream(
        self, stream: AsyncGenerator[str, None], url: str, chunk_num: int
    ) -> List[Dict]:
        """Parses a stream of text assumed to contain JSON objects, one per line."""
        items = []
        buffer = ""
        processed_len = 0
        decoder = json.JSONDecoder()

        try:
            async for text_chunk in stream:
                if not text_chunk:  # Handle potential None sentinel from stream end
                    continue
                buffer += text_chunk
                # Attempt to decode JSON objects from the buffer incrementally
                while True:
                    buffer_trimmed = buffer[processed_len:].lstrip()
                    if not buffer_trimmed:
                        break  # Only whitespace left

                    current_start_index = len(buffer) - len(buffer_trimmed)

                    try:
                        # Try to decode the *first* JSON object
                        obj, end_index_rel = decoder.raw_decode(buffer_trimmed)
                        end_index_abs = current_start_index + end_index_rel

                        if isinstance(obj, dict) and "title" in obj and "link" in obj:
                            # Basic validation passed
                            # TODO: Directly save asynchronously?
                            items.append(obj)
                        else:
                            logger.warning(
                                f"Skipping invalid/incomplete object from LLM stream for {url} (chunk {chunk_num}): {str(obj)[:100]}"
                            )

                        processed_len = end_index_abs  # Move past the processed object

                    except json.JSONDecodeError:
                        # Not enough data for a complete object yet, or invalid JSON start
                        break  # Wait for more data
                    except Exception as inner_e:
                        logger.error(
                            f"Error decoding object in stream for {url} (chunk {chunk_num}): {inner_e}",
                            exc_info=True,
                        )
                        # search for '{'.
                        index = buffer_trimmed.find("{")
                        if index != -1:
                            # Skip characters before '{'
                            processed_len = current_start_index + index
                        else:
                            # Discard buffer to potentially recover
                            processed_len = len(buffer)
                        break

            # Process any remaining valid JSON in the buffer after stream ends
            buffer_trimmed = buffer[processed_len:].lstrip()
            while buffer_trimmed:
                current_start_index = len(buffer) - len(buffer_trimmed)
                try:
                    obj, end_index_rel = decoder.raw_decode(buffer_trimmed)
                    end_index_abs = current_start_index + end_index_rel
                    if isinstance(obj, dict) and "title" in obj and "link" in obj:
                        items.append(obj)
                    processed_len = end_index_abs
                    buffer_trimmed = buffer[
                        processed_len:
                    ].lstrip()  # Continue processing buffer
                except json.JSONDecodeError:
                    logger.warning(
                        f"Partial/invalid JSON object at end of stream buffer for {url} (chunk {chunk_num}): {buffer_trimmed[:100]}"
                    )
                    break  # Cannot parse further
                except Exception as final_e:
                    logger.error(
                        f"Error decoding final object in stream buffer for {url} (chunk {chunk_num}): {final_e}",
                        exc_info=True,
                    )
                    break

        except Exception as e:
            logger.error(
                f"Error processing LLM stream with JSON parser for {url} (chunk {chunk_num}): {e}",
                exc_info=True,
            )

        return items

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
