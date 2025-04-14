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
from typing import List, Dict, Optional, Tuple, Callable, AsyncGenerator, Any
from datetime import datetime
from urllib.parse import urljoin

from src.core.crawler import AiohttpCrawler, PlaywrightCrawler
from src.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)
from src.services.llm_client import LLMClient
from src.utils.parse import parse_markdown_analysis_output
from src.utils.token_utils import get_token_size

logger = logging.getLogger(__name__)

# Default LLM model for extraction
DEFAULT_EXTRACTION_MODEL = "deepseek-v3-250324"
MAX_MARKDOWN_TOKENS = 20480  # 20k
MAX_OUTPUT_TOKENS = 16384  # 16k
MAX_INPUT_TOKENS = 131072 - MAX_OUTPUT_TOKENS  # updated to 128k - 16k


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
        on_stream_chunk_update: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        Fetch, extract, and save news from specified source IDs using non-streaming LLM.
        Reports progress per URL via on_url_status_update callback.

        Args:
            source_ids: List of source IDs to fetch. None means fetch all.
            on_url_status_update: Callback receiving (url, status, details).
            on_stream_chunk_update: Callback receiving stream chunk.
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

        logger.info(f"Crawling {len(urls_to_crawl)} sources...")

        # --- Decide Crawler ---
        # Using Playwright as per original code context
        crawler = PlaywrightCrawler(headless=True)
        # Alternative: crawler = AiohttpCrawler() if preferred

        try:
            # --- Process URLs ---
            async for crawl_result in crawler.process_urls(
                urls_to_crawl, output_format="markdown", scroll_pages=False
            ):
                processed_url_count += 1
                url = crawl_result.get("original_url", "")
                markdown = crawl_result.get("content")
                source_info = url_to_source_info.get(url)

                if not source_info:
                    logger.warning(f"Received crawl result for unknown URL: {url}")
                    continue

                # Report crawl status via the *first* callback
                if on_url_status_update:
                    status = "Crawled - Success" if markdown else "Crawled - Failed"
                    details = (
                        ""
                        if markdown
                        else crawl_result.get("error", "Unknown crawl error")
                    )
                    on_url_status_update(url, status, details)

                if markdown:
                    logger.info(f"Successfully crawled markdown for: {url}")
                    task = asyncio.create_task(
                        self._extract_and_save_items_sequentially(
                            url,
                            markdown,
                            source_info,
                            on_url_status_update,
                            on_stream_chunk_update,
                        )
                    )
                    all_extraction_tasks.append(task)
                else:
                    logger.warning(
                        f"Failed to get markdown for: {url}, error: {crawl_result.get('error', 'Unknown error')}"
                    )

        except Exception as crawl_error:
            logger.error(f"Error during crawling phase: {crawl_error}", exc_info=True)
            # Report to stream
            if on_stream_chunk_update:
                on_stream_chunk_update(f"[ERROR] Crawling failed: {crawl_error}\n")

        logger.info(
            f"Crawling phase finished. Processed URLs: {processed_url_count}. Waiting for extraction tasks..."
        )

        if all_extraction_tasks:
            results = await asyncio.gather(
                *all_extraction_tasks, return_exceptions=True
            )
            for i, result in enumerate(results):
                task_url = f"Task {i}"  # Placeholder, ideally get URL from result
                saved_count = 0
                task_exception = None

                if isinstance(result, Exception):
                    task_exception = result
                    # Report exception to stream
                    if on_stream_chunk_update:
                        on_stream_chunk_update(
                            f"[ERROR] Extraction task failed: {task_exception}\n"
                        )

                elif isinstance(result, tuple) and len(result) == 2:
                    task_url, saved_count_or_error = result
                    if isinstance(saved_count_or_error, int):
                        saved_count = saved_count_or_error
                        # Report success for this URL to stream (optional)
                        # if on_stream_chunk_update:
                        #    on_stream_chunk_update(f"[DONE] {task_url} - Saved {saved_count} items.\n")
                    elif isinstance(
                        saved_count_or_error, Exception
                    ):  # Check if it's an Exception
                        task_exception = saved_count_or_error
                        # Report specific error for this URL via URL status callback
                        if on_url_status_update:
                            on_url_status_update(
                                task_url,
                                "Error",
                                f"Extraction Failed: {task_exception}",
                            )
                        # Also report to stream
                        if on_stream_chunk_update:
                            on_stream_chunk_update(
                                f"[ERROR] Processing {task_url} failed: {task_exception}\n"
                            )
                    else:  # Treat other non-int as error string
                        err_str = str(saved_count_or_error)
                        if on_url_status_update:
                            on_url_status_update(
                                task_url, "Error", f"Extraction Failed: {err_str}"
                            )
                        if on_stream_chunk_update:
                            on_stream_chunk_update(
                                f"[ERROR] Processing {task_url} failed: {err_str}\n"
                            )

                if task_exception:
                    logger.error(
                        f"Error during extraction/saving task for {task_url}: {task_exception}",
                        exc_info=isinstance(task_exception, Exception),
                    )
                else:
                    total_saved_count += saved_count

        else:
            logger.info("No extraction tasks were started.")
            if on_stream_chunk_update:
                on_stream_chunk_update("[INFO] No extraction tasks needed.\n")

        logger.info(
            f"News fetching process completed. Total items saved across all sources: {total_saved_count}"
        )
        return total_saved_count

    async def _extract_and_save_items_sequentially(
        self,
        url: str,
        markdown: str,
        source_info: Dict[str, Any],
        on_url_status_update: Optional[Callable[[str, str, str], None]],
        on_stream_chunk_update: Optional[Callable[[str], None]],
    ) -> Tuple[str, Any]:  # Return URL and (count or error)
        """
        Helper coroutine: Extracts items from markdown using non-streaming LLM,
        collects them, and saves them in a single batch. Reports status updates.

        Args:
            url: The source URL being processed.
            markdown: The crawled markdown content.
            source_info: Dictionary containing info about the source.
            on_url_status_update: Callback for URL-specific status updates.
            on_stream_chunk_update: Callback for LLM stream chunks.
        Returns:
            Tuple of (URL, Number of saved items OR Error object/string).
        """

        saved_item_count = 0  # Track of items saved for this URL
        try:  # Wrap the whole process for better error reporting per URL
            if not markdown or not markdown.strip():
                if on_url_status_update:
                    on_url_status_update(url, "Skipped", "No markdown content")
                return url, 0  # Return 0 saved

            # --- Token Check and Chunking (if needed) ---
            token_size = get_token_size(markdown)
            if on_url_status_update:
                on_url_status_update(
                    url, "Processing", f"Checking token size ({token_size})"
                )
            markdown_chunks = [markdown]
            num_chunks = 1
            if token_size > MAX_INPUT_TOKENS:
                num_chunks = (token_size // MAX_INPUT_TOKENS) + 1
                try:
                    markdown_chunks = self._get_chunks(markdown, num_chunks)
                    log_msg = f"Splitting markdown for {url} into {len(markdown_chunks)} chunks ({token_size} tokens)."
                    logger.info(log_msg)
                    if on_url_status_update:
                        on_url_status_update(
                            url,
                            "Processing",
                            f"Splitting into {len(markdown_chunks)} chunks",
                        )
                except Exception as e:
                    log_msg = f"Error splitting markdown for {url}: {e}. Processing as single chunk."
                    logger.error(log_msg, exc_info=True)
                    markdown_chunks = [markdown]  # Fallback to single chunk
                    num_chunks = 1
                    if on_url_status_update:
                        on_url_status_update(
                            url, "Processing", "Split failed, using single chunk"
                        )

            # --- Process Chunks ---
            all_parsed_results_for_url = (
                []
            )  # Collect results from all chunks for this URL

            for i, chunk_content in enumerate(markdown_chunks):
                if not chunk_content or not chunk_content.strip():
                    logger.debug(f"Skipping empty chunk {i+1}/{num_chunks} for {url}")
                    continue

                chunk_status_prefix = f"Chunk {i+1}/{num_chunks}"
                status_msg_llm = f"{chunk_status_prefix} Extracting links..."
                if on_url_status_update:
                    on_url_status_update(url, "Extracting (LLM)", status_msg_llm)
                if on_stream_chunk_update:
                    on_stream_chunk_update(f"[INFO] {url} - {status_msg_llm}\n")
                logger.info(
                    f"Processing chunk {i+1}/{num_chunks} for {url} (Link Extraction)..."
                )

                # 1. Extract Links from Chunk
                link_extraction_prompt = self.build_link_extraction_prompt(
                    url, chunk_content
                )
                links_str = await self._llm_client.get_completion_content(
                    model=DEFAULT_EXTRACTION_MODEL,
                    messages=[{"role": "user", "content": link_extraction_prompt}],
                    max_tokens=8192,
                    temperature=0.0,
                )

                if not links_str or not links_str.strip():
                    logger.warning(
                        f"LLM returned no links for chunk {i+1}/{num_chunks} ({url})."
                    )
                    status_msg = f"{chunk_status_prefix} No links found."
                    if on_url_status_update:
                        on_url_status_update(url, "Processing", status_msg)
                    if on_stream_chunk_update:
                        on_stream_chunk_update(f"[INFO] {url} - {status_msg}\n")
                    continue  # Move to the next chunk

                # 2. Crawl Extracted Links
                extracted_links = [
                    urljoin(url, link.strip())
                    for link in links_str.split("\n")
                    if link.strip()
                ]
                if not extracted_links:
                    logger.warning(
                        f"No valid links parsed from LLM output for chunk {i+1}/{num_chunks} ({url})."
                    )
                    continue

                status_msg_crawl = f"{chunk_status_prefix} Crawling {len(extracted_links)} extracted links..."
                if on_url_status_update:
                    on_url_status_update(url, "Crawling Links", status_msg_crawl)
                if on_stream_chunk_update:
                    on_stream_chunk_update(f"[INFO] {url} - {status_msg_crawl}\n")
                logger.info(
                    f"Crawling {len(extracted_links)} extracted links for chunk {i+1}/{num_chunks} of {url}..."
                )

                crawler = AiohttpCrawler()  # Use Aiohttp for sub-crawls
                sub_crawl_results = []
                try:
                    async for crawl_result in crawler.process_urls(
                        extracted_links,
                        output_format="markdown",
                        markdownify_options={"strip": ["img"]},
                    ):
                        if crawl_result and crawl_result.get("content"):
                            sub_crawl_results.append(crawl_result)
                        elif crawl_result:
                            crawl_err_msg = f"Sub-crawl failed for {crawl_result.get('original_url')}: {crawl_result.get('error', 'No content')}"
                            logger.warning(crawl_err_msg)
                except Exception as sub_crawl_err:
                    err_msg = (
                        f"{chunk_status_prefix} Error during sub-crawl: {sub_crawl_err}"
                    )
                    logger.error(err_msg, exc_info=True)
                    if on_url_status_update:
                        on_url_status_update(url, "Error", err_msg)
                    # Decide whether to continue with next chunk or fail the whole URL? Let's continue for robustness.
                    continue

                if not sub_crawl_results:
                    status_msg_no_content = f"{chunk_status_prefix} No content found from {len(extracted_links)} extracted links."
                    logger.warning(status_msg_no_content)
                    if on_url_status_update:
                        on_url_status_update(url, "Processing", status_msg_no_content)
                    continue

                # 3. Analyze Crawled Content using Streaming LLM
                status_msg_analyze = f"{chunk_status_prefix} Analyzing content from {len(sub_crawl_results)} links..."
                if on_url_status_update:
                    on_url_status_update(url, "Analyzing (LLM)", status_msg_analyze)
                if on_stream_chunk_update:
                    on_stream_chunk_update(
                        f"---\n[INFO] {url} - {status_msg_analyze}\n---\n"
                    )  # Add separators for stream clarity
                logger.info(
                    f"Analyzing content from {len(sub_crawl_results)} links for chunk {i+1}/{num_chunks} of {url}..."
                )

                analysis_prompt = self.build_content_analysis_prompt(sub_crawl_results)
                token_check_analysis = get_token_size(analysis_prompt)
                logger.debug(
                    f"Analysis prompt token size for chunk {i+1}: {token_check_analysis}"
                )
                if token_check_analysis > MAX_INPUT_TOKENS:
                    err_msg = f"{chunk_status_prefix} Analysis prompt too large ({token_check_analysis} tokens), skipping analysis."
                    logger.error(err_msg)
                    if on_url_status_update:
                        on_url_status_update(url, "Error", err_msg)
                    if on_stream_chunk_update:
                        on_stream_chunk_update(f"[ERROR] {url} - {err_msg}\n")
                    continue

                # --- Use streaming ---
                analysis_result_markdown = ""
                stream_generator = await self._llm_client.stream_completion_content(
                    model=DEFAULT_EXTRACTION_MODEL,
                    messages=[{"role": "user", "content": analysis_prompt}],
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.8,
                )

                if stream_generator:
                    try:
                        async for chunk in stream_generator:
                            analysis_result_markdown += chunk
                            if on_stream_chunk_update:
                                on_stream_chunk_update(chunk)
                    except Exception as stream_err:
                        err_msg = f"{chunk_status_prefix} Error during LLM stream: {stream_err}"
                        logger.error(err_msg, exc_info=True)
                        if on_url_status_update:
                            on_url_status_update(url, "Error", err_msg)
                        analysis_result_markdown = ""  # Reset on error
                else:
                    # Stream initiation failed (already logged by llm_client)
                    status_msg = (
                        f"{chunk_status_prefix} Failed to start LLM analysis stream."
                    )
                    if on_url_status_update:
                        on_url_status_update(url, "Error", status_msg)
                    analysis_result_markdown = ""

                # 4. Parse and Collect Results for the Chunk
                if analysis_result_markdown:
                    try:
                        parsed_items = parse_markdown_analysis_output(
                            analysis_result_markdown
                        )
                        logger.info(
                            f"Parsed {len(parsed_items)} items from analysis of chunk {i+1}/{num_chunks} ({url})."
                        )

                        if parsed_items:
                            items_to_add = [
                                {
                                    **item,
                                    "source_name": source_info["name"],
                                    "category_name": source_info["category_name"],
                                    "source_id": source_info["id"],
                                    "category_id": source_info["category_id"],
                                }
                                for item in parsed_items
                            ]
                            all_parsed_results_for_url.extend(items_to_add)
                            status_msg = f"{chunk_status_prefix} Parsed {len(parsed_items)} items."
                            if on_url_status_update:
                                on_url_status_update(url, "Processing", status_msg)
                        else:
                            status_msg = f"{chunk_status_prefix} LLM analysis completed but no items parsed."
                            logger.warning(status_msg)
                            if on_url_status_update:
                                on_url_status_update(url, "Processing", status_msg)

                    except Exception as parse_err:
                        err_msg = f"{chunk_status_prefix} Error parsing LLM analysis output: {parse_err}"
                        logger.error(err_msg, exc_info=True)
                        if on_url_status_update:
                            on_url_status_update(url, "Error", err_msg)

            # --- End Chunk Loop ---

            # 5. Save All Collected Results for the URL
            if all_parsed_results_for_url:
                status_msg_save = f"Saving {len(all_parsed_results_for_url)} items..."
                if on_url_status_update:
                    on_url_status_update(url, "Saving", status_msg_save)
                logger.info(
                    f"Saving {len(all_parsed_results_for_url)} items for {url}..."
                )

                try:
                    added_count, skipped_count = self._news_repo.add_batch(
                        all_parsed_results_for_url
                    )
                    saved_item_count = added_count  # Store the count for this URL
                    status_msg_saved = (
                        f"Complete - Saved {added_count}, Skipped {skipped_count}"
                    )
                    if on_url_status_update:
                        on_url_status_update(url, "Complete", status_msg_saved)
                except Exception as db_err:
                    err_msg = f"Database error saving items: {db_err}"
                    logger.error(err_msg, exc_info=True)
                    if on_url_status_update:
                        on_url_status_update(url, "Error", err_msg)
                    # Return the DB error instead of count
                    return url, db_err
            else:
                # No items parsed/collected from any chunk
                status_msg_no_items = "Complete - No new items found/parsed."
                if on_url_status_update:
                    on_url_status_update(url, "Complete", status_msg_no_items)

            return url, saved_item_count  # Return successful count for this URL

        except Exception as e:
            err_msg = f"Critical error processing URL {url}: {e}"
            logger.error(err_msg, exc_info=True)
            # Report error via both callbacks if possible
            if on_url_status_update:
                on_url_status_update(url, "Error", f"Processing Failed: {e}")
            return url, e  # Return the exception

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
            end_line = (
                start_line + lines_per_chunk if i < num_chunks - 1 else total_lines
            )
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

        return [
            chunk for chunk in chunks if chunk and chunk.strip()
        ]  # Remove empty chunks

    def build_link_extraction_prompt(self, url: str, markdown_content: str) -> str:
        prompt = f"""
You are an intelligent information assistant.

You are provided with a markdown-formatted document crawled from a web page.  
The markdown may contain multiple content entries — such as news headlines, forum posts, academic papers, technical blogs, or other article-like links.  
Your task is to **identify which links if any, require deeper understanding by retrieving the full content**, and output those URLs in plain text format — one per line.

### Instructions:
- Only include links that point to real content pages (e.g., full articles, papers, posts, tutorials).
- Ignore any non-informational links such as login pages, navigation, ads, search/category pages, or QR codes.
- Skip any links that are clearly irrelevant or repetitive.
- If a link is relative (e.g., starts with `/articles/xxx`), please convert it into a full absolute URL using the base: {url}
- Do **not** summarize or analyze the content.
- Do **not** output any explanations, formatting, markdown, or JSON.
- Simply output a list of full URLs, one per line.

---
markdown-formatted document:
{markdown_content}

Please list the URLs that should be deeply analyzed:
"""
        return prompt

    def build_content_analysis_prompt(
        self, markdown_contents: List[Dict[str, Any]]
    ) -> str:
        # 多篇内容聚合分析 markdown 输出 prompt
        prompt = """
You are an intelligent content summarization assistant.  
You are given a collection of web pages in Markdown format. Each page represents a full article.  
Your job is to extract key information from each article and present it in a **well-structured, human-readable Markdown format** suitable for quick scanning and understanding.

### Your task:

1. For **each article**, extract and organize the following information:
   - **Title**: Inferred from the content or heading, must not be empty.
   - **Original Link**: Provided with the article (you will find it right above each markdown block).
   - **Publication Date**: If a specific date is mentioned in the content, include it in `YYYY-MM-DD` format.
   - **Summary**: A concise overview within 100 words that captures the core message of the article.
   - **Analysis**: Provide meaningful insights based on the article content. The angle of analysis should be derived from the context — such as technical innovations, social impact, trends, strategic implications, etc. Do not use a fixed template. Make the analysis content-specific and informative.

2. Markdown formatting guidelines:
   - Use `###` for the title of each article.
   - Display the link and date using `🔗` and `📅` icons.
   - Use labels like `**Summary:**` and `**Analysis:**` for clear formatting.
   - Ensure the content is easy to read in both English and Chinese.
   - Avoid promotional content, ads, irrelevant metadata, or UI elements.
   - Your output should use **the same language as the original article**.  
     Do not translate or switch languages.  
     If the article is written in Chinese, your summary and analysis should also be in Chinese.

### Example Output (for reference only):

---

### Huawei Unveils CloudMatrix 384 Super Node

🔗 https://www.example.com/articles/huawei-cloudmatrix  
📅 2025-04-10

**Summary:** Huawei launched the CloudMatrix 384 super node, enabling scaled deployment of Ascend AI infrastructure and significantly boosting model training efficiency.

**Analysis:** This marks a major step in Huawei’s commitment to building a domestic AI ecosystem. The CloudMatrix platform is poised to drive accelerated adoption of AI in sectors like healthcare, finance, and manufacturing, reinforcing Huawei’s leadership in AI cloud infrastructure.

---

### Introduction to Self-Attention in Transformer Models

🔗 https://www.example.com/tutorial/transformer-self-attention  
📅 2024-11-22

**Summary:** This tutorial explains the concept of self-attention in Transformer models with diagrams and PyTorch examples. It is targeted at ML beginners.

**Analysis:** The article offers a clear pedagogical breakdown of one of the most important deep learning mechanisms. It bridges theoretical concepts and practical code, making it an ideal entry point for those aiming to implement custom Transformer blocks.

---

Now process the following articles. For each one, the original link is included above the markdown content:

"""

        for i, markdown_content in enumerate(markdown_contents):
            prompt += f"\n\n[Article {i+1}] Link: {markdown_content.get('original_url')}\n{markdown_content.get('content')}\n"

        prompt += "\n\nPlease summarize and analyze each article in Markdown format, following the structure and style shown above."
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
        return [
            {"id": r[0], "name": r[1], "url": r[2], "category_id": r[3]} for r in rows
        ]

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
