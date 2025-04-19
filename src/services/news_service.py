# src/services/news_service.py (Refactored)
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
NewsService Module
- Coordinates retrieval, processing, analysis, and storage of news content.
- Utilizes an LLM for link extraction and in-depth content summarization.
"""

import logging
import asyncio
import re
from typing import List, Dict, Optional, Tuple, Callable, Any
from urllib.parse import urljoin

# Crawler for asynchronous HTTP requests
from src.core.crawler import AiohttpCrawler

# Repository interfaces for database operations
from src.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)

# Client to interact with the LLM API
from src.services.llm_client import LLMClient

# Utility for parsing structured output from LLM analysis
from src.utils.markdown_utils import (
    clean_markdown_links,
    strip_markdown_divider,
    strip_markdown_links,
)
from src.utils.parse import parse_markdown_analysis_output

# Utility for measuring token counts for LLM input/output constraints
from src.utils.token_utils import get_token_size

# HTML cleaning and conversion to Markdown
from src.utils.html_utils import clean_and_format_html

# system prompt
from src.utils.prompt import (
    EXTRACT_ARTICLE_LINKS_SYSTEM_PROMPT,
    EXTRACT_SUMMARIZE_ARTICLE_BATCH_SYSTEM_PROMPT,
)

# Configure module-level logger
logger = logging.getLogger(__name__)

# Default model identifier for link extraction and analysis
DEFAULT_EXTRACTION_MODEL = "deepseek-v3-250324"
# Maximum tokens allowed in LLM's output response
MAX_OUTPUT_TOKENS = 16384
# Maximum tokens allowed in LLM's input prompt
MAX_INPUT_TOKENS = 131072 - 2 * MAX_OUTPUT_TOKENS


class NewsService:
    """
    Service class responsible for:
    - Fetching HTML content from news sources (handled externally now, e.g., by Controller/Worker).
    - Processing fetched HTML: cleaning, formatting, chunking.
    - Extracting relevant links using LLM.
    - Crawling extracted links for sub-content.
    - Performing LLM-driven content analysis on sub-content.
    - Parsing analysis output and saving structured news items.
    - Providing CRUD operations for news, sources, and categories.
    """

    def __init__(
        self,
        news_repo: NewsRepository,
        source_repo: NewsSourceRepository,
        category_repo: NewsCategoryRepository,
        llm_client: LLMClient,
    ):
        # Database repositories
        self._news_repo = news_repo
        self._source_repo = source_repo
        self._category_repo = category_repo
        # LLM client for content extraction and analysis
        self._llm_client = llm_client

    # -------------------------------------------------------------------------
    # Main Orchestration Method (Called by Worker/Controller)
    # -------------------------------------------------------------------------

    async def _process_html_and_analyze(
        self,
        url: str,
        html_content: str,
        source_info: Dict[str, Any],
        on_status_update: Optional[Callable[[str, str, str], None]],
    ) -> Tuple[int, str, Optional[Exception]]:
        """
        Processes HTML content from a single news source URL. This is the main
        entry point for the processing logic called by the worker.

        Workflow:
          1. Prepare Markdown from HTML.
          2. Chunk Markdown if necessary.
          3. Process each chunk:
             - Extract links via LLM.
             - Crawl extracted links for sub-content.
             - Analyze sub-content via LLM (potentially chunked).
             - Parse analysis results.
          4. Save all parsed items to the database.

        Args:
            url: The original URL of the news source.
            html_content: The raw HTML content fetched from the URL.
            source_info: Dictionary containing metadata about the source (id, name, category_id, etc.).
            on_status_update: Optional callback function for reporting progress updates.
                              Expected signature: on_status_update(url, status_message, details)

        Returns:
            Tuple[int, str, Optional[Exception]]
            - saved_item_count: Number of successfully stored news items.
            - analysis_result_markdown: Raw Markdown result from the final content analysis step(s).
            - processing_error: Any exception or error message encountered during processing.
        """

        # Helper for status updates
        def _status_update(status: str, details: str = ""):
            if on_status_update:
                try:
                    on_status_update(url, status, details)
                except Exception as e:
                    logger.error(f"Status update callback error for {url}: {e}")

        saved_item_count = 0
        analysis_result_markdown = ""  # Store concatenated results if chunked
        processing_error = None
        all_parsed_results_for_url: List[Dict[str, Any]] = []

        try:
            # Step 1: Clean HTML and prepare initial Markdown
            markdown = self._clean_and_prepare_markdown(
                url, html_content, _status_update
            )
            if not markdown:
                return 0, "", None  # Skipped due to empty content

            # Step 2: Chunk initial Markdown if too large
            token_size = get_token_size(markdown)
            _status_update("Token Check", f"Initial Markdown tokens: {token_size}")
            markdown_chunks = [markdown]
            num_chunks = 1
            if token_size > 40960:
                num_chunks = (token_size // 40960) + 1
                try:
                    markdown_chunks = self._get_chunks(markdown, num_chunks)
                    logger.info(
                        f"Chunked initial markdown for {url} into {len(markdown_chunks)} segments."
                    )
                    _status_update(
                        "Chunking", f"{len(markdown_chunks)} initial segments"
                    )
                except Exception as e:
                    logger.error(
                        f"Initial chunk splitting failed for {url}: {e}", exc_info=True
                    )
                    _status_update("Chunk Err", "Proceeding with single segment")
                    markdown_chunks = [markdown]  # Fallback
                    num_chunks = 1

            # Step 3: Process each chunk
            for i, chunk_content in enumerate(markdown_chunks, start=1):
                status_prefix = f"C{i}/{num_chunks}" if num_chunks > 1 else "Processing"
                if not chunk_content.strip():
                    logger.debug(f"Skipped empty chunk {i}/{num_chunks} for {url}")
                    continue

                # Step 3a: Extract and crawl links
                sub_content_map, chunk_error = await self._extract_and_crawl_links(
                    url, chunk_content, status_prefix, _status_update
                )
                if chunk_error:
                    processing_error = chunk_error  # Store first error encountered
                if not sub_content_map:
                    continue  # Skip analysis if no sub-content found or crawl failed

                # Step 3b: Analyze the collected sub-content
                chunk_analysis_result, analyze_error = await self._analyze_content(
                    url, sub_content_map, status_prefix, _status_update
                )
                if analyze_error:
                    processing_error = (
                        processing_error or analyze_error
                    )  # Keep first error
                if not chunk_analysis_result:
                    continue  # Skip parsing if analysis failed or returned empty

                # Aggregate analysis results if chunking occurred
                if num_chunks > 1:
                    analysis_result_markdown += (
                        f"\n\n--- Chunk {i} Analysis ---\n{chunk_analysis_result}"
                    )
                else:
                    analysis_result_markdown = chunk_analysis_result

                # Step 3c: Parse results from this chunk's analysis
                parsed_items, parse_error = self._parse_analysis_results(
                    url,
                    chunk_analysis_result,
                    sub_content_map,
                    source_info,
                    status_prefix,
                    _status_update,
                )
                if parse_error:
                    processing_error = (
                        processing_error or parse_error
                    )  # Keep first error
                if parsed_items:
                    all_parsed_results_for_url.extend(parsed_items)

            # End of chunk processing loop

            # Step 4: Save all accumulated results to the database
            saved_item_count, db_error = self._save_results_to_db(
                url, all_parsed_results_for_url, _status_update
            )
            if db_error:
                processing_error = processing_error or db_error

            # Determine final status based on errors encountered
            final_status = "Complete" if not processing_error else "Complete*"
            _status_update(
                final_status,
                f"Added: {saved_item_count}, Skipped: {len(all_parsed_results_for_url) - saved_item_count}",
            )

            return saved_item_count, analysis_result_markdown.strip(), processing_error

        except Exception as critical_err:
            logger.error(
                f"Fatal processing error for {url}: {critical_err}", exc_info=True
            )
            _status_update("Fatal Error", str(critical_err))
            return 0, analysis_result_markdown.strip(), critical_err

    # -------------------------------------------------------------------------
    # Private Helper Methods for Processing Steps
    # -------------------------------------------------------------------------

    def _clean_and_prepare_markdown(
        self, url: str, html_content: str, _status_update: Callable[[str, str], None]
    ) -> Optional[str]:
        """Cleans HTML, converts to Markdown, and cleans links."""
        _status_update("HTML Proc", "Cleaning and formatting HTML")
        if not html_content or not html_content.strip():
            _status_update("Skipped", "Empty HTML content")
            return None

        try:
            markdown = clean_and_format_html(
                html_content=html_content,
                base_url=url,
                output_format="markdown",
            )
            if not markdown or not markdown.strip():
                _status_update("Skipped", "No Markdown after cleaning")
                return None

            # Clean markdown links immediately after conversion
            cleaned_markdown = clean_markdown_links(markdown)
            _status_update("HTML Done", "Cleaned HTML to Markdown")
            return cleaned_markdown

        except Exception as e:
            logger.error(
                f"Error during HTML cleaning/formatting for {url}: {e}", exc_info=True
            )
            _status_update("HTML Error", str(e))
            return None  # Treat as skippable error for this step

    async def _extract_and_crawl_links(
        self,
        base_url: str,
        markdown_content: str,
        status_prefix: str,
        _status_update: Callable[[str, str], None],
    ) -> Tuple[Dict[str, str], Optional[Exception]]:
        """Extracts links using LLM, crawls them, and returns processed sub-content."""
        sub_content_map: Dict[str, str] = {}
        error = None

        _status_update(f"{status_prefix} Link Ext", "Invoking LLM for links")
        link_prompt = self.build_link_extraction_prompt(base_url, markdown_content)
        links_str = await self._llm_client.get_completion_content(
            model=DEFAULT_EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACT_ARTICLE_LINKS_SYSTEM_PROMPT},
                {"role": "user", "content": link_prompt},
            ],
            max_tokens=4096,  # Sufficient for a list of links
            temperature=0.0,  # Low temp for deterministic extraction
        )

        if not links_str or not links_str.strip():
            logger.warning(f"No links returned by LLM for {base_url} ({status_prefix})")
            _status_update(f"{status_prefix} No Links", "")
            return sub_content_map, None  # Not an error, just no links

        # Parse and normalize URLs
        extracted_links = [
            urljoin(base_url, link.strip())
            for link in links_str.splitlines()
            if link.strip() and link.strip() != base_url  # Exclude self-links
        ]
        if not extracted_links:
            logger.warning(
                f"LLM link output produced no valid URLs for {base_url} ({status_prefix})"
            )
            _status_update(f"{status_prefix} No Links", "Parsing failed")
            return sub_content_map, None

        _status_update(f"{status_prefix} Crawling", f"{len(extracted_links)} URLs")
        logger.info(
            f"Crawling {len(extracted_links)} links for {base_url} ({status_prefix})"
        )
        sub_crawler = AiohttpCrawler(max_concurrent_requests=5, request_timeout=15)
        try:
            async for crawl_result in sub_crawler.process_urls(extracted_links):
                if crawl_result.get("error"):
                    logger.warning(
                        f"Sub-crawl failed for {crawl_result.get('original_url')}: {crawl_result['error']}"
                    )
                    continue
                if not crawl_result.get("content"):
                    logger.warning(
                        f"Sub-crawl returned empty content for {crawl_result.get('original_url')}"
                    )
                    continue

                sub_url = crawl_result.get(
                    "final_url", crawl_result.get("original_url")
                )
                if not sub_url:
                    continue

                # Clean sub-page HTML to Markdown, stripping images and links
                sub_markdown = clean_and_format_html(
                    html_content=crawl_result["content"],
                    base_url=sub_url,
                    output_format="markdown",
                    markdownify_options={
                        "strip": ["img"]
                    },  # Strip images during conversion
                )
                if not sub_markdown:
                    continue

                # Remove remaining inline Markdown links for cleaner analysis input
                cleaned_content = strip_markdown_links(sub_markdown)
                cleaned_content = strip_markdown_divider(cleaned_content)
                sub_content_map[sub_url] = cleaned_content.strip()

        except Exception as sub_err:
            logger.error(
                f"Sub-crawl error for {base_url} ({status_prefix}): {sub_err}",
                exc_info=True,
            )
            _status_update(f"{status_prefix} CrawlErr", str(sub_err))
            error = sub_err  # Propagate crawl error

        if not sub_content_map:
            _status_update(f"{status_prefix} No Sub-Content", "")

        return sub_content_map, error

    async def _analyze_content(
        self,
        url: str,
        sub_content_map: Dict[str, str],
        status_prefix: str,
        _status_update: Callable[[str, str], None],
    ) -> Tuple[str, Optional[Exception]]:
        """Analyzes the collected sub-content using LLM, handling chunking if needed."""
        analysis_result_markdown = ""
        error = None

        _status_update(f"{status_prefix} Analyzing", f"{len(sub_content_map)} items")
        analysis_prompt = self.build_content_analysis_prompt(sub_content_map)
        print(len(sub_content_map))
        with open(f"analysis_prompt.txt", "w", encoding="utf-8") as f:
            f.write(analysis_prompt)
        prompt_tokens = get_token_size(analysis_prompt)
        logger.debug(
            f"Analysis prompt tokens for {url} ({status_prefix}): {prompt_tokens}"
        )

        try:
            # Handle prompt chunking if it exceeds input limit
            if prompt_tokens > MAX_INPUT_TOKENS:
                num_prompt_chunks = (prompt_tokens // MAX_INPUT_TOKENS) + 1
                # 将 sub_content_map 的 key 均分到 num_prompt_chunks 个子字典中，并重建每个子字典对应的 prompt
                chunk_maps: List[Dict[str, str]] = []
                keys = list(sub_content_map.keys())
                total = len(keys)
                if total < num_prompt_chunks:
                    logger.warning(
                        f"Not enough content to chunk for {url} ({status_prefix}), skipping chunking."
                    )
                    return (
                        "",
                        "Token limit exceeded, not enough content to chunk for {url} ({status_prefix}), skipping chunking.",
                    )
                size = total // num_prompt_chunks
                for i in range(num_prompt_chunks):
                    start = i * size
                    end = start + size if i < num_prompt_chunks - 1 else total
                    part_keys = keys[start:end]
                    if not part_keys:
                        continue
                    chunk_maps.append({k: sub_content_map[k] for k in part_keys})
                # 根据每个子字典重建 prompt 列表
                prompt_chunks = [
                    self.build_content_analysis_prompt(chunk) for chunk in chunk_maps
                ]
                logger.info(
                    f"Analysis prompt chunking for {url} ({status_prefix}): {len(prompt_chunks)} parts."
                )
                _status_update(
                    f"{status_prefix} Chunking", f"{len(prompt_chunks)} analysis parts"
                )

                partial_results: List[str] = []
                for j, p_chunk in enumerate(prompt_chunks, start=1):
                    _status_update(
                        f"{status_prefix} Analyzing {j}/{len(prompt_chunks)}",
                        "LLM analysis",
                    )
                    chunk_result = await self._llm_client.get_completion_content(
                        model=DEFAULT_EXTRACTION_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": EXTRACT_SUMMARIZE_ARTICLE_BATCH_SYSTEM_PROMPT,
                            },
                            {"role": "user", "content": p_chunk},
                        ],
                        max_tokens=MAX_OUTPUT_TOKENS,
                        temperature=0.8,  # Higher temp for creative summarization
                    )
                    if chunk_result and chunk_result.strip():
                        partial_results.append(chunk_result)
                    else:
                        logger.warning(
                            f"Empty result for analysis prompt chunk {j}/{len(prompt_chunks)} at {url}"
                        )

                analysis_result_markdown = "\n\n---\n\n".join(
                    partial_results
                )  # Combine results
            else:
                # Analyze in one go
                analysis_result_markdown = await self._llm_client.get_completion_content(
                    model=DEFAULT_EXTRACTION_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": EXTRACT_SUMMARIZE_ARTICLE_BATCH_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": analysis_prompt},
                    ],
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.8,
                )

            # Check final result
            if not analysis_result_markdown or not analysis_result_markdown.strip():
                err_msg = (
                    f"LLM analysis returned no content for {url} ({status_prefix})"
                )
                logger.error(err_msg)
                _status_update(f"{status_prefix} Analyze Err", "Empty LLM response")
                error = Exception(err_msg)
            else:
                _status_update(f"{status_prefix} Analyzed", "LLM analysis complete")

        except Exception as analyze_err:
            logger.error(
                f"LLM analysis failed for {url} ({status_prefix}): {analyze_err}",
                exc_info=True,
            )
            _status_update(f"{status_prefix} Analyze Err", str(analyze_err))
            error = analyze_err

        return analysis_result_markdown, error

    def _parse_analysis_results(
        self,
        url: str,
        analysis_result_markdown: str,
        sub_content_map: Dict[str, str],
        source_info: Dict[str, Any],
        status_prefix: str,
        _status_update: Callable[[str, str], None],
    ) -> Tuple[List[Dict[str, Any]], Optional[Exception]]:
        """Parses the LLM's analysis markdown and prepares items for saving."""
        parsed_items_list: List[Dict[str, Any]] = []
        error = None

        try:
            parsed_items = parse_markdown_analysis_output(analysis_result_markdown)
            logger.info(
                f"Parsed {len(parsed_items)} items from {url} ({status_prefix}) analysis."
            )

            if parsed_items:
                items_to_add = [
                    {
                        **item,  # Contains title, link, date, summary
                        "content": sub_content_map.get(
                            item["link"], ""
                        ),  # Add original content
                        "source_name": source_info["name"],
                        "category_name": source_info["category_name"],
                        "source_id": source_info["id"],
                        "category_id": source_info["category_id"],
                    }
                    for item in parsed_items
                    if item.get("link")  # Ensure link exists
                ]
                parsed_items_list.extend(items_to_add)
                _status_update(
                    f"{status_prefix} Parsed", f"{len(items_to_add)} items ready"
                )
            else:
                logger.warning(
                    f"No actionable items parsed for {url} ({status_prefix})"
                )
                _status_update(f"{status_prefix} Parse Empty", "No items detected")

        except Exception as parse_err:
            logger.error(
                f"Parsing error for LLM output of {url} ({status_prefix}): {parse_err}",
                exc_info=True,
            )
            _status_update(f"{status_prefix} Parse Err", str(parse_err))
            error = parse_err

        return parsed_items_list, error

    def _save_results_to_db(
        self,
        url: str,
        parsed_items: List[Dict[str, Any]],
        _status_update: Callable[[str, str], None],
    ) -> Tuple[int, Optional[Exception]]:
        """Saves the parsed items to the database."""
        saved_count = 0
        error = None

        if not parsed_items:
            return 0, None  # Nothing to save

        _status_update("Saving", f"{len(parsed_items)} items")
        logger.info(f"Saving {len(parsed_items)} items for {url}")
        try:
            added_count, skipped_count = self._news_repo.add_batch(parsed_items)
            saved_count = added_count
            logger.info(
                f"Database save for {url}: Added {added_count}, Skipped {skipped_count}"
            )
            # Status update is handled by the calling orchestrator method
        except Exception as db_err:
            logger.error(f"Database save error for {url}: {db_err}", exc_info=True)
            _status_update("DB Error", str(db_err))
            error = db_err

        return saved_count, error

    # -------------------------------------------------------------------------
    # Text Chunking Helper
    # -------------------------------------------------------------------------

    def _get_chunks(self, text: str, num_chunks: int) -> List[str]:
        """
        Split input text into approximately equal-sized chunks by lines.
        """
        lines = text.splitlines()
        if not lines:
            return []
        total_lines = len(lines)
        lines_per_chunk = max(1, total_lines // num_chunks)
        chunks: List[str] = []
        start_index = 0
        for i in range(num_chunks):
            end_index = (
                start_index + lines_per_chunk if i < num_chunks - 1 else total_lines
            )
            end_index = min(end_index, total_lines)
            if start_index < end_index:
                chunks.append("\n".join(lines[start_index:end_index]))
            start_index = end_index
            if start_index >= total_lines:
                break
        return [chunk for chunk in chunks if chunk.strip()]

    # -------------------------------------------------------------------------
    # Prompt Construction Helpers
    # -------------------------------------------------------------------------

    def build_link_extraction_prompt(self, url: str, markdown_content: str) -> str:
        """Constructs the prompt for LLM link extraction."""
        prompt = f"""
Base URL: {url}
Markdown:
{markdown_content}
"""
        return prompt

    def build_content_analysis_prompt(self, content_map: Dict[str, str]) -> str:
        """Constructs the prompt for LLM content analysis."""
        # (Prompt content remains the same as original)
        if not content_map:
            return ""

        prompt = ""
        for url, content in content_map.items():
            prompt += f"<Article>\n"
            prompt += f"Original Link: {url}\n"
            prompt += f"Markdown Content:\n{content}\n"
            prompt += f"</Article>\n\n"

        prompt += "Please summarize each article in Markdown format, following the structure and style shown above."
        return prompt

    # -------------------------------------------------------------------------
    # Public CRUD Methods (Pass-through to Repositories)
    # -------------------------------------------------------------------------

    # --- News Item Methods ---
    def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single news item by its unique identifier."""
        return self._news_repo.get_by_id(news_id)

    def get_all_news(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieve a paginated list of news items."""
        return self._news_repo.get_all(limit, offset)

    def delete_news(self, news_id: int) -> bool:
        """Delete a news item by its ID."""
        return self._news_repo.delete(news_id)

    def clear_all_news(self) -> bool:
        """Remove all news items from the database. Use with caution."""
        logger.warning("Executing clear_all_news - all news data will be removed.")
        return self._news_repo.clear_all()

    # --- Category Methods ---
    def get_all_categories(self) -> List[Tuple[int, str]]:
        """List all categories (ID, Name)."""
        return self._category_repo.get_all()

    def get_all_categories_with_counts(self) -> List[Tuple[int, str, int]]:
        """List all categories (ID, Name, Source Count)."""
        return self._category_repo.get_with_source_count()

    def add_category(self, name: str) -> Optional[int]:
        """Add a new category. Returns the new category ID or None."""
        return self._category_repo.add(name)

    def update_category(self, category_id: int, new_name: str) -> bool:
        """Rename an existing category."""
        return self._category_repo.update(category_id, new_name)

    def delete_category(self, category_id: int) -> bool:
        """Delete a category and its associated news sources."""
        logger.warning(
            f"Deleting category ID {category_id} will also delete its sources."
        )
        return self._category_repo.delete(category_id)

    # --- Source Methods ---
    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Retrieve all news sources with category metadata."""
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
        """Retrieve news sources filtered by a specific category ID."""
        rows = self._source_repo.get_by_category(category_id)
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

    def add_source(self, name: str, url: str, category_name: str) -> Optional[int]:
        """Add a new source. Creates category if missing. Returns new source ID or None."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(
                    f"Failed to add/find category '{category_name}' for new source."
                )
                return None
        else:
            category_id = category[0]
        return self._source_repo.add(name, url, category_id)

    def update_source(
        self, source_id: int, name: str, url: str, category_name: str
    ) -> bool:
        """Update an existing source. Creates category if missing."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(
                    f"Failed to add/find category '{category_name}' for updating source."
                )
                return False
        else:
            category_id = category[0]
        return self._source_repo.update(source_id, name, url, category_id)

    def delete_source(self, source_id: int) -> bool:
        """Delete a news source by its ID."""
        return self._source_repo.delete(source_id)
