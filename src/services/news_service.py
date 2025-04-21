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
from typing import AsyncGenerator, List, Dict, Optional, Tuple, Callable, Any
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

# Utilities for processing content and LLM output
from src.utils.markdown_utils import (
    clean_markdown_links,
    strip_markdown_divider,
    strip_markdown_links,
)
from src.utils.parse import parse_json_from_text
from src.utils.token_utils import get_token_size
from src.utils.html_utils import clean_and_format_html, extract_metadata_from_article_html
from src.utils.prompt import (
    SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS,
    SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
    SYSTEM_PROMPT_ANALYZE_CONTENT,
)

# Configure module-level logger
logger = logging.getLogger(__name__)

# Constants for LLM model and token limits
DEFAULT_EXTRACTION_MODEL = "deepseek-v3-250324"
MAX_OUTPUT_TOKENS = 16384  # Max tokens for LLM output
MAX_INPUT_TOKENS = 131072 - 2 * MAX_OUTPUT_TOKENS  # Max tokens for LLM input prompt

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

    # -------------------------------------------------------------------------
    # Main Orchestration Method (Called by Worker/Controller)
    # -------------------------------------------------------------------------
    async def _process_html_and_analyze(
        self,
        url: str,
        html_content: str,
        source_info: Dict[str, Any],
        on_status_update: Optional[Callable[[str, str, str], None]],
        llm_client: LLMClient,
    ) -> Tuple[int, str, Optional[Exception]]:
        """
        Asynchronous entry point to process HTML content and analyze news articles.
        1. Convert HTML to Markdown.
        2. Chunk Markdown if too large.
        3. For each chunk:
            a. Extract and crawl links.
            b. Analyze sub-articles via LLM.
            c. Parse analysis results.
        4. Save all parsed items to the database.

        Args:
            url: Source page URL.
            html_content: Raw HTML fetched from the URL.
            source_info: Metadata about the source (id, name, category, etc.).
            on_status_update: Optional callback for progress reporting.
            llm_client: Instance of LLMClient for API interaction.

        Returns:
            saved_item_count (int): Number of saved news items.
            analysis_result_markdown (str): Markdown summary of parsed items.
            processing_error (Exception|None): Any error encountered.
        """
        # Internal helper for unified status reporting
        def _status_update(status: str, details: str = ""):
            if on_status_update:
                try:
                    on_status_update(url, status, details)
                except Exception as e:
                    logger.error(f"Status update callback error for {url}: {e}")

        saved_item_count = 0
        analysis_result: List[Dict[str, Any]] = []
        processing_error: Optional[Exception] = None
        all_parsed_results_for_url: List[Dict[str, Any]] = []

        try:
            # Step 1: Clean HTML and produce Markdown
            markdown = self._clean_and_prepare_markdown(url, html_content, _status_update)
            if not markdown:
                # Skip processing if no valid Markdown generated
                return 0, "", None

            # Step 2: Evaluate token size and chunk if exceeding threshold
            token_size = get_token_size(markdown)
            _status_update("Token Check", f"Initial Markdown tokens: {token_size}")
            markdown_chunks = [markdown]
            num_chunks = 1
            if token_size > 40960:
                num_chunks = (token_size // 40960) + 1
                try:
                    # Split long Markdown into line-based chunks
                    markdown_chunks = self._get_chunks(markdown, num_chunks)
                    logger.info(f"Chunked initial markdown for {url} into {len(markdown_chunks)} segments.")
                    _status_update("Chunking", f"{len(markdown_chunks)} initial segments")
                except Exception as e:
                    logger.error(f"Initial chunk splitting failed for {url}: {e}", exc_info=True)
                    # Fallback to single chunk on error
                    _status_update("Chunk Err", "Proceeding with single segment")
                    markdown_chunks = [markdown]
                    num_chunks = 1

            # Step 3: Process each Markdown chunk
            for i, chunk_content in enumerate(markdown_chunks, start=1):
                status_prefix = f"C{i}/{num_chunks}" if num_chunks > 1 else "Processing"
                if not chunk_content.strip():
                    logger.debug(f"Skipped empty chunk {i}/{num_chunks} for {url}")
                    continue

                # 3a: Link extraction and crawling
                sub_structure_data_map, chunk_error = await self._extract_and_crawl_links(
                    url, chunk_content, status_prefix, _status_update, llm_client
                )
                if chunk_error:
                    processing_error = chunk_error
                if not sub_structure_data_map:
                    # Skip analysis if no sub-articles found
                    continue

                # 3b: Content analysis via LLM (with chunking support)
                chunk_analysis_result, analyze_error = await self._analyze_content(
                    url, sub_structure_data_map, status_prefix, _status_update, llm_client
                )
                if analyze_error:
                    processing_error = processing_error or analyze_error
                if not chunk_analysis_result:
                    continue

                # Aggregate analysis results for multi-chunk runs
                if num_chunks > 1:
                    analysis_result.extend(chunk_analysis_result)
                else:
                    analysis_result = chunk_analysis_result

                # 3c: Parse analysis output into structured items
                parsed_items, parse_error = self._parse_analysis_results(
                    url, chunk_analysis_result, sub_structure_data_map,
                    source_info, status_prefix, _status_update
                )
                if parse_error:
                    processing_error = processing_error or parse_error
                if parsed_items:
                    all_parsed_results_for_url.extend(parsed_items)

            # Step 4: Persist accumulated results to the database
            saved_item_count, db_error = self._save_results_to_db(
                url, all_parsed_results_for_url, _status_update
            )
            if db_error:
                processing_error = processing_error or db_error

            # Finalize status with summary of added vs skipped items
            final_status = "Complete" if not processing_error else "Complete*"
            _status_update(
                final_status,
                f"Added: {saved_item_count}, Skipped: {len(all_parsed_results_for_url) - saved_item_count}"
            )

            # Format summary of parsed items as Markdown for logging/display
            analysis_result_markdown = "\n".join([
                f"### {item.get('title', '')}\n"
                f"🔗 {item.get('url', '')}\n"
                f"📅 {item.get('date', '')}\n"
                f"📝 {item.get('summary', '')}\n"
                for item in all_parsed_results_for_url
            ])

            return saved_item_count, analysis_result_markdown, processing_error

        except Exception as critical_err:
            # Catch any unexpected error and report as fatal
            logger.error(f"Fatal processing error for {url}: {critical_err}", exc_info=True)
            _status_update("Fatal Error", str(critical_err))
            return 0, "", critical_err

    # -------------------------------------------------------------------------
    # Private Helper Methods for Processing Steps
    # -------------------------------------------------------------------------
    def _clean_and_prepare_markdown(
        self, url: str, html_content: str, _status_update: Callable[[str, str], None]
    ) -> Optional[str]:
        """
        Clean raw HTML and convert it into Markdown format.
        - Removes unwanted tags/styles.
        - Normalizes links.
        """
        _status_update("HTML Proc", "Cleaning and formatting HTML")
        if not html_content or not html_content.strip():
            _status_update("Skipped", "Empty HTML content")
            return None

        try:
            # Convert HTML to markdown
            markdown = clean_and_format_html(
                html_content=html_content,
                base_url=url,
                output_format="markdown",
            )
            if not markdown or not markdown.strip():
                _status_update("Skipped", "No Markdown after cleaning")
                return None

            # Remove or adjust any residual markdown links
            cleaned_markdown = clean_markdown_links(markdown)
            _status_update("HTML Done", "Cleaned HTML to Markdown")
            return cleaned_markdown

        except Exception as e:
            logger.error(f"Error during HTML cleaning/formatting for {url}: {e}", exc_info=True)
            _status_update("HTML Error", str(e))
            return None  # Continue processing with next steps as skippable error

    async def _extract_and_crawl_links(
        self,
        base_url: str,
        markdown_content: str,
        status_prefix: str,
        _status_update: Callable[[str, str], None],
        llm_client: LLMClient,
    ) -> Tuple[Dict[str, str], Optional[Exception]]:
        """
        Extracts article links from Markdown using LLM and fetches sub-article content.
        Returns a mapping from sub-URL to its extracted metadata.
        """
        sub_structure_data_map: Dict[str, str] = {}
        error: Optional[Exception] = None

        # 1) Ask LLM to identify relevant links
        _status_update(f"{status_prefix} Link Ext", "Invoking LLM for links")
        link_prompt = self.build_link_extraction_prompt(base_url, markdown_content)
        links_str = await llm_client.get_completion_content(
            model=DEFAULT_EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS},
                {"role": "user", "content": link_prompt},
            ],
            max_tokens=4096,
            temperature=0.0,
        )

        # If LLM returned no links, skip without error
        if not links_str or not links_str.strip():
            logger.warning(f"No links returned by LLM for {base_url} ({status_prefix})")
            _status_update(f"{status_prefix} No Links", "")
            return sub_structure_data_map, None

        # Normalize and filter out self-links
        extracted_links = [
            urljoin(base_url, link.strip())
            for link in links_str.splitlines()
            if link.strip() and link.strip() != base_url
        ]
        if not extracted_links:
            logger.warning(f"LLM link output produced no valid URLs for {base_url} ({status_prefix})")
            _status_update(f"{status_prefix} No Links", "Parsing failed")
            return sub_structure_data_map, None

        # 2) Crawl each extracted link concurrently
        _status_update(f"{status_prefix} Crawling", f"{len(extracted_links)} URLs")
        logger.info(f"Crawling {len(extracted_links)} links for {base_url} ({status_prefix})")
        sub_crawler = AiohttpCrawler(max_concurrent_requests=5, request_timeout=15)
        try:
            async for crawl_result in sub_crawler.process_urls(extracted_links):
                # Skip any failed requests
                if crawl_result.get("error"):
                    logger.warning(f"Sub-crawl failed for {crawl_result.get('original_url')}: {crawl_result['error']}")
                    continue
                if not crawl_result.get("content"):
                    logger.warning(f"Sub-crawl returned empty content for {crawl_result.get('original_url')}")
                    continue

                sub_url = crawl_result.get("final_url", crawl_result.get("original_url"))
                if not sub_url:
                    continue

                # Extract structured data (title, date, content) from HTML
                structure_data = extract_metadata_from_article_html(
                    html_content=crawl_result["content"],
                    base_url=sub_url,
                )
                if not structure_data:
                    continue

                sub_structure_data_map[sub_url] = structure_data

        except Exception as sub_err:
            # Record crawl errors and propagate
            logger.error(f"Sub-crawl error for {base_url} ({status_prefix}): {sub_err}", exc_info=True)
            _status_update(f"{status_prefix} CrawlErr", str(sub_err))
            error = sub_err

        if not sub_structure_data_map:
            _status_update(f"{status_prefix} No Sub-Content", "")

        return sub_structure_data_map, error

    async def _analyze_content(
        self,
        url: str,
        sub_structure_data_map: Dict[str, str],
        status_prefix: str,
        _status_update: Callable[[str, str], None],
        llm_client: LLMClient,
    ) -> Tuple[str, Optional[Exception]]:
        """
        Run LLM-driven summarization on collected sub-article data.
        Supports prompt chunking if the input size exceeds token limits.
        """
        analysis_result: List[Dict[str, str]] = []
        error: Optional[Exception] = None

        _status_update(f"{status_prefix} Analyzing", f"{len(sub_structure_data_map)} items")
        analysis_prompt = self.build_content_analysis_prompt(sub_structure_data_map)
        prompt_tokens = get_token_size(analysis_prompt)
        logger.debug(f"Analysis prompt tokens for {url} ({status_prefix}): {prompt_tokens}")

        try:
            # If prompt size too large, split into smaller batches
            if prompt_tokens > MAX_INPUT_TOKENS:
                num_prompt_chunks = (prompt_tokens // MAX_INPUT_TOKENS) + 1
                chunk_maps: List[Dict[str, str]] = []
                keys = list(sub_structure_data_map.keys())
                total = len(keys)

                if total < num_prompt_chunks:
                    logger.warning(f"Not enough content to chunk for {url} ({status_prefix}), skipping chunking.")
                    return "", "Token limit exceeded, not enough content to chunk."

                size = total // num_prompt_chunks
                for i in range(num_prompt_chunks):
                    start = i * size
                    end = start + size if i < num_prompt_chunks - 1 else total
                    part_keys = keys[start:end]
                    if part_keys:
                        chunk_maps.append({k: sub_structure_data_map[k] for k in part_keys})

                # Build separate prompts for each chunk
                prompt_chunks = [
                    self.build_content_analysis_prompt(chunk_map) for chunk_map in chunk_maps
                ]
                logger.info(f"Analysis prompt chunking for {url} ({status_prefix}): {len(prompt_chunks)} parts.")
                _status_update(f"{status_prefix} Chunking", f"{len(prompt_chunks)} analysis parts")

                partial_results: List[Dict[str, str]] = []
                for idx, p_chunk in enumerate(prompt_chunks, start=1):
                    _status_update(f"{status_prefix} Analyzing {idx}/{len(prompt_chunks)}", "LLM analysis")
                    llm_result = await llm_client.get_completion_content(
                        model=DEFAULT_EXTRACTION_MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH},
                            {"role": "user", "content": p_chunk},
                        ],
                        max_tokens=MAX_OUTPUT_TOKENS,
                        temperature=0.8,
                    )
                    # Parse JSON response
                    try:
                        json_result = parse_json_from_text(llm_result)
                        partial_results.extend(json_result)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON for {url} ({status_prefix})")
                    except Exception as e:
                        logger.error(f"Failed to parse JSON for {url} ({status_prefix}): {e}")

                analysis_result = partial_results or []

            else:
                # Single-call analysis for smaller prompts
                llm_result = await llm_client.get_completion_content(
                    model=DEFAULT_EXTRACTION_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH},
                        {"role": "user", "content": analysis_prompt},
                    ],
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.8,
                )
                try:
                    analysis_result = parse_json_from_text(llm_result)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON for {url} ({status_prefix})")
                    analysis_result = []
                except Exception as e:
                    logger.error(f"Failed to parse JSON for {url} ({status_prefix}): {e}")
                    analysis_result = []

            # Validate final analysis output
            if not analysis_result:
                error_msg = f"LLM analysis returned no content for {url} ({status_prefix})"
                logger.error(error_msg)
                _status_update(f"{status_prefix} Analyze Err", "Empty LLM response")
                error = Exception(error_msg)
            else:
                _status_update(f"{status_prefix} Analyzed", "LLM analysis complete")

        except Exception as analyze_err:
            # Catch any analysis errors
            logger.error(f"LLM analysis failed for {url} ({status_prefix}): {analyze_err}", exc_info=True)
            _status_update(f"{status_prefix} Analyze Err", str(analyze_err))
            error = analyze_err

        return analysis_result, error

    def _parse_analysis_results(
        self,
        url: str,
        analysis_result: List[Dict[str, str]],
        sub_structure_data_map: Dict[str, Dict[str, Any]],
        source_info: Dict[str, Any],
        status_prefix: str,
        _status_update: Callable[[str, str], None],
    ) -> Tuple[List[Dict[str, Any]], Optional[Exception]]:
        """
        Convert LLM analysis output into structured news item dictionaries ready for database insertion.
        """
        parsed_items_list: List[Dict[str, Any]] = []
        error: Optional[Exception] = None

        try:
            if analysis_result:
                # Merge analysis fields with original metadata
                items_to_add = []
                for item in analysis_result:
                    if item.get("url"):
                        parsed = {
                            **item,
                            "title": sub_structure_data_map.get(item["url"], {}).get("title", ""),
                            "date": sub_structure_data_map.get(item["url"], {}).get("date", ""),
                            "content": sub_structure_data_map.get(item["url"], {}).get("content", ""),
                            "source_name": source_info["name"],
                            "category_name": source_info["category_name"],
                            "source_id": source_info["id"],
                            "category_id": source_info["category_id"],
                        }
                        items_to_add.append(parsed)
                parsed_items_list.extend(items_to_add)
                _status_update(f"{status_prefix} Parsed", f"{len(items_to_add)} items ready")
            else:
                # No items extracted from analysis
                logger.warning(f"No actionable items parsed for {url} ({status_prefix})")
                _status_update(f"{status_prefix} Parse Empty", "No items detected")
        except Exception as parse_err:
            # Handle parsing exceptions
            logger.error(f"Parsing error for LLM output of {url} ({status_prefix}): {parse_err}", exc_info=True)
            _status_update(f"{status_prefix} Parse Err", str(parse_err))
            error = parse_err

        return parsed_items_list, error

    def _save_results_to_db(
        self,
        url: str,
        parsed_items: List[dict],
        _status_update: Callable[[str, str], None]
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

        _status_update("Saving", f"{len(parsed_items)} items")
        logger.info(f"Saving {len(parsed_items)} items for {url}")
        try:
            added_count, skipped_count = self._news_repo.add_batch(parsed_items)
            saved_count = added_count
            logger.info(f"Database save for {url}: Added {added_count}, Skipped {skipped_count}")
        except Exception as db_err:
            # Log DB save failures
            logger.error(f"Database save error for {url}: {db_err}", exc_info=True)
            _status_update("DB Error", str(db_err))
            error = db_err

        return saved_count, error

    # -------------------------------------------------------------------------
    # Text Chunking Helper
    # -------------------------------------------------------------------------
    def _get_chunks(self, text: str, num_chunks: int) -> List[str]:
        """
        Split the input text into roughly equal-sized chunks by line count.
        """
        lines = text.splitlines()
        if not lines:
            return []

        total_lines = len(lines)
        lines_per_chunk = max(1, total_lines // num_chunks)
        chunks: List[str] = []
        start_idx = 0

        for i in range(num_chunks):
            end_idx = start_idx + lines_per_chunk if i < num_chunks - 1 else total_lines
            end_idx = min(end_idx, total_lines)
            if start_idx < end_idx:
                chunks.append("\n".join(lines[start_idx:end_idx]))
            start_idx = end_idx
            if start_idx >= total_lines:
                break

        return [chunk for chunk in chunks if chunk.strip()]

    # -------------------------------------------------------------------------
    # Prompt Construction Helpers
    # -------------------------------------------------------------------------
    def build_link_extraction_prompt(self, url: str, markdown_content: str) -> str:
        """Create the prompt for link extraction LLM call."""
        prompt = f"""
Base URL: {url}
Markdown:
{markdown_content}
"""
        return prompt

    def build_content_analysis_prompt(self, structure_data_map: Dict[str, str]) -> str:
        """Build the prompt containing article metadata to guide LLM summarization."""
        if not structure_data_map:
            return ""

        prompt_parts: List[str] = []
        for article_url, data in structure_data_map.items():
            prompt_parts.append("<Article>")
            prompt_parts.append(f"Title: {data['title']}")
            prompt_parts.append(f"Url: {data['url']}")
            prompt_parts.append(f"Date: {data['date']}")
            prompt_parts.append("Content:")
            prompt_parts.append(data["content"])
            prompt_parts.append("</Article>\n")

        prompt_parts.append("Please summarize each article in Markdown format, following the structure and style shown above.")
        return "\n".join(prompt_parts)

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
        """List all categories with count of sources."""
        return self._category_repo.get_with_source_count()

    def add_category(self, name: str) -> Optional[int]:
        """Add a new category; returns new category ID on success."""
        return self._category_repo.add(name)

    def update_category(self, category_id: int, new_name: str) -> bool:
        """Rename an existing category."""
        return self._category_repo.update(category_id, new_name)

    def delete_category(self, category_id: int) -> bool:
        """Delete a category and all its associated news sources."""
        logger.warning(f"Deleting category ID {category_id} will also delete its sources.")
        return self._category_repo.delete(category_id)

    # --- Source Methods ---
    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Retrieve all news sources along with their category metadata."""
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
        """Retrieve news sources filtered by specific category ID."""
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
        """Add a new source; create category if it does not exist."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(f"Failed to add/find category '{category_name}' for new source.")
                return None
        else:
            category_id = category[0]
        return self._source_repo.add(name, url, category_id)

    def update_source(self, source_id: int, name: str, url: str, category_name: str) -> bool:
        """Update existing source info; create category if missing."""
        category = self._category_repo.get_by_name(category_name)
        if not category:
            category_id = self._category_repo.add(category_name)
            if not category_id:
                logger.error(f"Failed to add/find category '{category_name}' for updating source.")
                return False
        else:
            category_id = category[0]
        return self._source_repo.update(source_id, name, url, category_id)

    def delete_source(self, source_id: int) -> bool:
        """Delete a news source by its ID."""
        return self._source_repo.delete(source_id)

    async def analyze_single_content(
        self,
        system_prompt: str,
        user_prompt: str,
        api_key: str,
        base_url: str
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM analysis for a single piece of content.
        Yields analysis fragments as they are generated by the model.
        """
        from src.services.llm_client import LLMClient

        try:
            # Instantiate a temporary LLM client in async streaming mode
            llm_client = LLMClient(api_key=api_key, base_url=base_url, async_mode=True)

            # Start streaming completion from the LLM
            stream_generator = await llm_client.stream_completion_content(
                model=DEFAULT_EXTRACTION_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.7,
            )

            # Ensure the stream was successfully initiated
            if stream_generator is None:
                logger.error("LLM stream initiation failed.")
                yield "\n\nAnalysis process failed: Unable to start streaming analysis."
                return

            # Yield each chunk of output as it arrives
            async for chunk in stream_generator:
                yield chunk

        except Exception as e:
            # Handle any streaming errors
            logger.error(f"LLM streaming analysis failed: {e}", exc_info=True)
            yield f"\n\nAnalysis process failed: {e}"

    def update_news_analysis(self, news_id: int, analysis_text: str) -> bool:
        """
        Update the 'analysis' field of an existing news record.
        Returns True on success, False otherwise.
        """
        try:
            return self._news_repo.update_analysis(news_id, analysis_text)
        except Exception as e:
            logger.error(f"Error updating analysis field for news ID {news_id}: {e}", exc_info=True)
            return False
