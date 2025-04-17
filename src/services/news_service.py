# src/services/news_service.py (Modified)
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News service module
Responsible for the acquisition, storage, retrieval, and management of news
Refactored processing logic.
"""

import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Callable, Any
from urllib.parse import urljoin

# Import necessary components
from src.core.crawler import AiohttpCrawler  # Keep both potentially
from src.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
)
from src.services.llm_client import LLMClient
from src.utils.parse import parse_markdown_analysis_output
from src.utils.token_utils import get_token_size
from src.utils.html_process import clean_and_format_html  # Import HTML processing

logger = logging.getLogger(__name__)

# Default LLM model and token limits (remain the same)
DEFAULT_EXTRACTION_MODEL = "deepseek-v3-250324"
MAX_OUTPUT_TOKENS = 16384
MAX_INPUT_TOKENS = 131072 - MAX_OUTPUT_TOKENS


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
        self._processing_lock = (
            asyncio.Lock()
        )  # Lock for potential shared resources if needed

    # --- News Fetching and Processing ---

    async def _process_html_and_analyze(
        self,
        url: str,
        html_content: str,
        source_info: Dict[str, Any],
        on_status_update: Optional[
            Callable[[str, str, str], None]
        ],  # url, status, details
    ) -> Any:
        """
        Processes the given HTML content for a single source URL.
        This includes cleaning HTML, extracting links, sub-crawling, analyzing, and saving.
        Designed to be called by the ProcessingWorker thread.

        Args:
            url: The original source URL.
            html_content: Raw HTML content from the initial crawl.
            source_info: Dictionary containing info about the source.
            on_status_update: Callback for status updates (url, status, details).

        Returns:
            Tuple containing (saved_item_count: int, analysis_result_markdown: str, error: Optional[Exception/str])
            Returns (0, "", error) on failure.
            Returns (count, result_md, None) on success.
        """

        # --- Helper function for status updates ---
        def _status_update(status: str, details: str = ""):
            if on_status_update:
                try:
                    # Limit detail length visually if needed, but keep full detail for logs
                    on_status_update(url, status, details)
                except Exception as e:
                    logger.error(f"Error in status update callback for {url}: {e}")

        # --- Variables Initialization ---
        saved_item_count = 0
        analysis_result_markdown = ""  # Store the final analysis result here
        processing_error = None  # Store potential error object/string

        try:
            _status_update("HTML Proc", "Starting HTML processing")  # Shortened
            if not html_content or not html_content.strip():
                _status_update("Skipped", "No HTML content")  # Shortened
                return 0, "", None

            # 1. Process HTML (Clean and Format)
            markdown = clean_and_format_html(
                html_content=html_content,
                base_url=url,
                output_format="markdown",
            )

            if not markdown or not markdown.strip():
                _status_update("Skipped", "Empty content")  # Shortened
                return 0, "", None

            _status_update("HTML Done", "HTML processed to Markdown")  # Shortened
            token_size = get_token_size(markdown)
            _status_update("Token Check", f"Size: {token_size}")  # Shortened

            # --- Chunking Logic ---
            markdown_chunks = [markdown]
            num_chunks = 1
            if token_size > MAX_INPUT_TOKENS:
                num_chunks = (token_size // MAX_INPUT_TOKENS) + 1
                try:
                    markdown_chunks = self._get_chunks(markdown, num_chunks)
                    log_msg = f"Splitting markdown for {url} into {len(markdown_chunks)} chunks ({token_size} tokens)."
                    logger.info(log_msg)
                    _status_update(
                        "Chunking", f"Split into {len(markdown_chunks)}"
                    )  # Shortened
                except Exception as e:
                    log_msg = f"Error splitting markdown for {url}: {e}. Processing as single chunk."
                    logger.error(log_msg, exc_info=True)
                    markdown_chunks = [markdown]
                    num_chunks = 1
                    _status_update("Chunk Err", "Using single chunk")  # Shortened

            # --- Process Chunks ---
            all_parsed_results_for_url = []
            all_sub_crawl_results = []

            for i, chunk_content in enumerate(markdown_chunks):
                if not chunk_content or not chunk_content.strip():
                    logger.debug(f"Skipping empty chunk {i+1}/{num_chunks} for {url}")
                    continue

                chunk_status_prefix = f"C{i+1}/{num_chunks}"
                _status_update(
                    f"{chunk_status_prefix} Link Extract", "Calling LLM..."
                )  # Shortened
                logger.info(
                    f"Processing chunk {i+1}/{num_chunks} for {url} (Link Extraction)..."
                )

                # 2. Extract Links from Chunk (Non-streaming)
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
                    _status_update(f"{chunk_status_prefix} No Links", "")  # Shortened
                    continue

                # 3. Crawl Extracted Links
                extracted_links = [
                    urljoin(url, link.strip())
                    for link in links_str.split("\n")
                    if link.strip() and link.strip() != url
                ]
                if not extracted_links:
                    logger.warning(
                        f"No valid unique links parsed from LLM output for chunk {i+1}/{num_chunks} ({url})."
                    )
                    continue

                _status_update(
                    f"{chunk_status_prefix} Crawling",
                    f"Crawling {len(extracted_links)} links...",  # Shortened
                )
                logger.info(
                    f"Crawling {len(extracted_links)} extracted links for chunk {i+1}/{num_chunks} of {url}..."
                )

                sub_crawler = AiohttpCrawler(
                    max_concurrent_requests=5, request_timeout=15
                )
                chunk_sub_crawl_results = []
                try:
                    async for crawl_result in sub_crawler.process_urls(extracted_links):
                        if crawl_result and crawl_result.get("content"):
                            sub_html = crawl_result["content"]
                            sub_url = crawl_result.get(
                                "final_url", crawl_result.get("original_url")
                            )
                            sub_markdown = clean_and_format_html(
                                sub_html,
                                sub_url,
                                "markdown",
                                markdownify_options={"strip": ["img"]},
                            )
                            if sub_markdown:
                                chunk_sub_crawl_results.append(
                                    {"original_url": sub_url, "content": sub_markdown}
                                )
                            else:
                                logger.warning(
                                    f"Sub-crawl content empty after markdownify for {sub_url}"
                                )
                        elif crawl_result:
                            logger.warning(
                                f"Sub-crawl failed for {crawl_result.get('original_url')}: {crawl_result.get('error', 'No content')}"
                            )
                except Exception as sub_crawl_err:
                    err_msg = f"Error during sub-crawl: {sub_crawl_err}"
                    logger.error(f"{chunk_status_prefix} {err_msg}", exc_info=True)
                    _status_update(
                        f"{chunk_status_prefix} Crawl Err", f"{sub_crawl_err}"
                    )  # Shortened
                    continue

                all_sub_crawl_results.extend(chunk_sub_crawl_results)

            # --- End Chunk Loop ---

            # 4. Analyze ALL Crawled Content (Non-Streaming LLM)
            if not all_sub_crawl_results:
                status_msg_no_content = "No content found from extracted links."
                logger.warning(f"{status_msg_no_content} for {url}")
                _status_update("No Sub-Content", "")  # Shortened
                # Decide if this should be an error or just complete with 0 saved
                return 0, "", None

            _status_update(
                "Analyzing",
                f"LLM analysis of {len(all_sub_crawl_results)} links...",  # Shortened
            )
            logger.info(
                f"Analyzing content from {len(all_sub_crawl_results)} links for {url}..."
            )

            analysis_prompt = self.build_content_analysis_prompt(all_sub_crawl_results)
            token_check_analysis = get_token_size(analysis_prompt)
            logger.debug(
                f"Analysis prompt token size for {url}: {token_check_analysis}"
            )

            if token_check_analysis > MAX_INPUT_TOKENS:
                err_msg = (
                    f"Analysis prompt too large ({token_check_analysis}), skipped."
                )
                logger.error(err_msg)
                _status_update("Error", "Prompt too large")  # Shortened
                processing_error = Exception(err_msg)  # Store error
                # analysis_result_markdown will be empty
            else:
                # Use non-streaming LLM call for analysis
                analysis_result_markdown = (
                    await self._llm_client.get_completion_content(
                        model=DEFAULT_EXTRACTION_MODEL,
                        messages=[{"role": "user", "content": analysis_prompt}],
                        max_tokens=MAX_OUTPUT_TOKENS,
                        temperature=0.8,
                    )
                )

                if not analysis_result_markdown:
                    err_msg = (
                        f"LLM analysis failed or returned empty content for {url}."
                    )
                    logger.error(err_msg)
                    _status_update("Analyze Err", "LLM Empty/Failed")  # Shortened
                    processing_error = Exception(err_msg)  # Store error
                    # analysis_result_markdown is already ""
                else:
                    _status_update("Analyzed", "Analysis complete.")  # Shortened

            # 5. Parse Analysis Result
            if analysis_result_markdown:
                try:
                    parsed_items = parse_markdown_analysis_output(
                        analysis_result_markdown
                    )
                    logger.info(
                        f"Parsed {len(parsed_items)} items from analysis of {url}."
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
                        _status_update(
                            "Parsed", f"Found {len(parsed_items)} items."
                        )  # Shortened
                    else:
                        status_msg_noparse = (
                            "LLM analysis completed but no items parsed."
                        )
                        logger.warning(f"{status_msg_noparse} for {url}")
                        _status_update("Parse Empty", "")  # Shortened

                except Exception as parse_err:
                    err_msg = f"Error parsing LLM analysis output: {parse_err}"
                    logger.error(err_msg, exc_info=True)
                    _status_update("Parse Err", f"{parse_err}")  # Shortened
                    processing_error = parse_err  # Store error, keep raw markdown

            # 6. Save All Collected Results for the URL
            if all_parsed_results_for_url:
                _status_update(
                    "Saving", f"Saving {len(all_parsed_results_for_url)} items..."
                )  # Shortened
                logger.info(
                    f"Saving {len(all_parsed_results_for_url)} items for {url}..."
                )
                try:
                    added_count, skipped_count = self._news_repo.add_batch(
                        all_parsed_results_for_url
                    )
                    saved_item_count = added_count
                    # Determine final status based on whether an error occurred earlier
                    final_status = (
                        "Complete" if not processing_error else "Complete*"
                    )  # Mark completion with prior error
                    _status_update(
                        final_status, f"Saved {added_count}, Skipped {skipped_count}"
                    )  # Shortened
                except Exception as db_err:
                    err_msg = f"Database error saving items: {db_err}"
                    logger.error(err_msg, exc_info=True)
                    _status_update("DB Error", f"{db_err}")  # Shortened
                    # Overwrite previous error if DB error is critical
                    processing_error = db_err
            else:
                # If parsing failed or no items were parsed
                final_status = "Complete" if not processing_error else "Complete*"
                _status_update(final_status, "No new items saved.")  # Shortened

            # Return successful count, the full analysis markdown, and any stored error
            return saved_item_count, analysis_result_markdown, processing_error

        except Exception as e:
            err_msg = f"Critical error processing URL {url}: {e}"
            logger.error(err_msg, exc_info=True)
            _status_update("Fatal Error", f"{e}")  # Shortened
            # Return 0 saved, potentially empty result, and the exception
            return 0, analysis_result_markdown, e

    # --- Helper Methods ---
    def _get_chunks(self, text: str, num_chunks: int) -> List[str]:
        """Split text into chunks of approximately equal size."""
        lines = text.splitlines()
        if not lines:
            return []
        total_lines = len(lines)
        lines_per_chunk = max(1, total_lines // num_chunks)
        chunks = []
        start_line = 0
        for i in range(num_chunks):
            end_line = (
                start_line + lines_per_chunk if i < num_chunks - 1 else total_lines
            )
            end_line = min(end_line, total_lines)
            if start_line < end_line:
                chunks.append("\n".join(lines[start_line:end_line]))
            start_line = end_line
            if start_line >= total_lines:
                break
        return [chunk for chunk in chunks if chunk and chunk.strip()]

    def build_link_extraction_prompt(self, url: str, markdown_content: str) -> str:
        """Build a prompt for link extraction from markdown content."""
        prompt = f"""
You are an intelligent information assistant.

You are provided with a markdown-formatted document crawled from a web page.
The markdown may contain multiple content entries — such as news headlines, forum posts, academic papers, technical blogs, or other article-like links.
Your task is to **identify which links if any, require deeper understanding by retrieving the full content**, and output those URLs in plain text format — one per line.

### Instructions:
- Only include links that point to real content pages (e.g., full articles, papers, posts, tutorials).
- Ignore any non-informational links such as login pages, navigation, ads, search/category pages, or QR codes.
- **Deduplicate** identical URLs; skip links that are clearly irrelevant or repetitive.
- If a link is **relative** (e.g., starts with `/articles/xxx`), convert it to an absolute URL using the base → {url}.
- As a heuristic, prefer URLs with **two or more path segments** or a clear file extension such as `.html`, `.pdf`, `.md` over bare domain roots.
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
        """Build a prompt for content analysis from a list of markdown contents."""
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
   - **Analysis**: Provide a **detailed, content‑specific analysis** in Markdown that focuses on the article’s effective information while automatically filtering out irrelevant or promotional details.  
     - Tailor the analysis to the article’s context (e.g., **academic contributions**, technical innovations, social impact, trends, strategic implications, etc.).  
     - Avoid a fixed template; let the structure follow the content.  
     - **Do not include `---` inside the analysis.**

2. Markdown formatting guidelines:
   - Use `###` for the title of each article.
   - Display the link and date using `🔗` and `📅` icons.
   - Use bold labels `**Summary:**` and `**Analysis:**` for clarity.  
   - Ensure the result is easy to read in both English and Chinese.  
   - **Write in the same language as the original article.** (If the article is in Chinese, your summary and analysis must also be in Chinese.)  
   - Omit ads, UI elements, and any irrelevant metadata.

### Example Output (for reference only):

---

### Huawei Unveils CloudMatrix 384 Super Node  
🔗 https://www.example.com/articles/huawei‑cloudmatrix  
📅 2025‑04‑10  

**Summary:** Huawei 发布 CloudMatrix 384 超节点，可大规模部署 Ascend AI 基础设施，显著提升模型训练效率。

**Analysis:**
- **技术突破：** CloudMatrix 384 通过高速互连和模块化设计，将 8 卡节点扩展至 384 卡，满足千亿参数大模型训练需求。
- **生态影响：** 该平台降低了国内 AI 基础设施门槛，促进医疗、金融、制造等行业加速采用国产 AI 方案。
- **战略意义：** 在美制裁背景下，此举强化了华为自研算力版图，推动本土 AI 产业链自主可控。

---

### Introduction to Self‑Attention in Transformer Models
🔗 https://www.example.com/tutorial/transformer‑self‑attention
📅 2024‑11‑22

**Summary:** 这篇教程通过图示与 PyTorch 示例讲解 Transformer 模型中的自注意力机制，面向机器学习初学者。

**Analysis:**
- **教学价值：** 文中将数学公式与可视化步骤结合，帮助读者直观理解 Query‑Key‑Value 计算过程。
- **实用示例：** 提供可直接运行的 PyTorch 代码片段，示范如何自定义多头注意力层。
- **趋势洞察：** 随着多模态 Transformer 的兴起，深入掌握自注意力机制已成为进入生成式 AI 领域的必备技能。

---

Now process the following articles. For each one, the original link is included above the markdown content:

"""

        for i, markdown_content in enumerate(markdown_contents):
            prompt += f"\n\n[Article {i+1}] Link: {markdown_content.get('original_url')}\n{markdown_content.get('content')}\n"

        prompt += "\n\nPlease summarize and analyze each article in Markdown format, following the structure and style shown above."
        return prompt

    # --- News Management ---
    def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        return self._news_repo.get_by_id(news_id)

    def get_all_news(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self._news_repo.get_all(limit, offset)

    def delete_news(self, news_id: int) -> bool:
        return self._news_repo.delete(news_id)

    def clear_all_news(self) -> bool:
        logger.warning("Executing clear_all_news - All news data will be removed.")
        return self._news_repo.clear_all()

    # --- Category and Source Management ---
    def get_all_categories(self) -> List[Tuple[int, str]]:
        return self._category_repo.get_all()

    def get_all_categories_with_counts(self) -> List[Tuple[int, str, int]]:
        return self._category_repo.get_with_source_count()

    def add_category(self, name: str) -> Optional[int]:
        return self._category_repo.add(name)

    def update_category(self, category_id: int, new_name: str) -> bool:
        return self._category_repo.update(category_id, new_name)

    def delete_category(self, category_id: int) -> bool:
        logger.warning(
            f"Deleting category ID {category_id} will also delete associated news sources."
        )
        return self._category_repo.delete(category_id)

    def get_all_sources(self) -> List[Dict[str, Any]]:
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
        return self._source_repo.delete(source_id)
