import json
import logging
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from backend.utils.html_utils import (
    clean_and_format_html,
    extract_metadata_from_article_html,
)
from backend.utils.markdown_utils import (
    clean_markdown_links,
    strip_javascript_links,
    strip_image_links,
)
from backend.utils.parse import parse_json_from_text
from backend.utils.prompt import (
    SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS,
    SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
)
from backend.utils.text_utils import get_chunks
from backend.utils.token_utils import get_token_size
from ..crawler import AiohttpCrawler, SeleniumCrawler
from ..llm.pool import LLMClientPool
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def fetch_news(
    url: str,
    llm_pool: LLMClientPool,
    exclude_links: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str, float, str, int], None]] = None,
) -> List[Dict[str, str]]:
    """
    Fetch news from a given URL using a crawler and an LLM pool.

    Args:
        url: The URL of the news to fetch.
        llm_pool: The LLM pool to use for fetching the news.
        crawler: The crawler to use for fetching the news.
        exclude_links: The links to exclude from the news.
        progress_callback: The callback to use for updating the progress of the news fetch.
            Accepts arguments: step, progress_percent, message, items_count=0

    Returns:
        A list of dictionaries containing the news summary.
        Each dictionary contains the following keys:
            - title: The title of the news.
            - url: The URL of the news.
            - date: The date of the news.
            - summary: The summary of the news.
            - content: The content of the news.
    """
    # 报告开始进行爬取操作
    if progress_callback:
        await progress_callback("crawling", 10, f"正在爬取页面: {url}")

    # 1) Crawl html content (contains news content and links to other pages) from url
    # and format it to cleaned markdown
    crawler_result = None
    async with SeleniumCrawler(
        chromedriver_path="C:\\software\\chromedriver-win32\\chromedriver.exe"
    ) as crawler:
        crawler_result = await crawler.fetch_single(url)

    if not crawler_result or crawler_result.get("error"):
        raise ValueError(f"Failed to crawl {url}: {crawler_result.get('error')}")

    html_content = crawler_result.get("content", "")
    if not html_content:
        raise ValueError(f"Failed to crawl {url}")

    cleaned_markdown = _clean_and_prepare_markdown(
        url=url, html_content=html_content, exclude_links=exclude_links
    )

    if not cleaned_markdown:
        raise ValueError("Failed to clean and prepare markdown")

    # 2) Extract links from the cleaned markdown
    if progress_callback:
        await progress_callback("extracting", 20, "正在从页面提取文章链接")

    # 2a) Evaluate token size and chunk if exceeding context window
    token_size = get_token_size(cleaned_markdown)
    markdown_chunks = [cleaned_markdown]
    num_chunks = 1
    if token_size > llm_pool._context_window:
        num_chunks = (token_size // llm_pool._context_window) + 1
        if progress_callback:
            await progress_callback(
                "chunking", 25, f"页面内容较大，正在分割为 {num_chunks} 个部分进行处理"
            )
        try:
            # Split long Markdown into line-based chunks
            markdown_chunks = get_chunks(cleaned_markdown, num_chunks)
        except Exception as e:
            # Fallback to single chunk on error
            markdown_chunks = [cleaned_markdown]
            num_chunks = 1
            if progress_callback:
                await progress_callback(
                    "warning", 25, f"内容分割失败，将作为单个块处理: {str(e)}"
                )

    # 2b) Extract content from each link from links in each chunk
    original_content_metadata_dict: Dict[str, Dict[str, str]] = (
        {}
    )  # key: link, value: metadata

    chunk_count = len(markdown_chunks)
    for i, chunk_content in enumerate(markdown_chunks):
        if not chunk_content.strip():
            continue

        if progress_callback and chunk_count > 1:
            await progress_callback(
                "processing",
                30 + (i * 10 / chunk_count),
                f"正在处理页面分块 {i+1}/{chunk_count}",
            )

        # Link extraction and crawling
        sub_original_content_metadata_dict = await _extract_and_crawl_links(
            url, chunk_content, llm_pool
        )

        if not sub_original_content_metadata_dict:
            # Skip analysis if no sub-articles found
            continue

        # Add each link and its metadata to the main dictionary
        original_content_metadata_dict.update(sub_original_content_metadata_dict)

    if not original_content_metadata_dict:
        raise ValueError("No original content metadata found")

    # 报告即将进行内容总结
    if progress_callback:
        await progress_callback(
            "analyzing",
            60,
            f"找到 {len(original_content_metadata_dict)} 个文章，正在进行分析和总结",
        )

    # 3) Summarize the original content
    summary_result = await summarize_content(
        url=url,
        original_content_metadata_dict=original_content_metadata_dict,
        llm_pool=llm_pool,
    )

    if not summary_result:
        raise ValueError("Failed to summarize the original content")

    # 报告完成
    if progress_callback:
        await progress_callback(
            "formatting", 90, f"已完成 {len(summary_result)} 个文章的提取与总结"
        )

    return summary_result


# -------------------------------------------------------------------------
# Private Helper Methods for Processing Steps
# -------------------------------------------------------------------------
def _clean_and_prepare_markdown(
    url: str, html_content: str, exclude_links: Optional[List[str]] = None
) -> Optional[str]:
    """
    Clean raw HTML and convert it into Markdown format.
    - Removes unwanted tags/styles.
    - Normalizes links.

    Args:
        url: The URL of the news.
        html_content: The HTML content of the news.
        exclude_links: The links to exclude from the news.

    Returns:
        The cleaned and prepared markdown content.
    """
    try:
        # Convert HTML to markdown
        cleaned_markdown = clean_and_format_html(
            html_content=html_content,
            base_url=url,
            output_format="markdown",
            exclude_selectors=[],
            exclude_tags=[],
        )

        cleaned_markdown = strip_image_links(cleaned_markdown)

        cleaned_markdown = strip_javascript_links(cleaned_markdown)

        # # Remove or adjust any residual markdown links
        # cleaned_markdown = clean_markdown_links(
        #     markdown, exclude_urls=exclude_links, base_url=url
        # )

        return cleaned_markdown
    except Exception as e:
        logger.error(
            f"Error during HTML cleaning/formatting for {url}: {e}", exc_info=True
        )
        return None


def build_link_extraction_prompt(url: str, markdown_content: str) -> str:
    """Create the prompt for link extraction LLM call."""
    prompt = f"""
<Base URL>
{url}
</Base URL>
<Markdown content>
{markdown_content}
</Markdown content>
"""
    return prompt


def build_content_analysis_prompt(
    original_content_metadata_dict: Dict[str, Dict[str, str]],
) -> str:
    """Build the prompt containing article metadata to guide LLM summarization."""
    if not original_content_metadata_dict:
        return ""

    prompt_parts: List[str] = []
    for article_url, data in original_content_metadata_dict.items():
        prompt_parts.append("<Article>")
        prompt_parts.append(f"Title: {data.get('title', 'Untitled')}")
        prompt_parts.append(f"Url: {data.get('url', article_url)}")
        prompt_parts.append(f"Date: {data.get('date', 'N/A')}")
        prompt_parts.append("Content:")
        prompt_parts.append(data.get("content", ""))
        prompt_parts.append("</Article>\n")

    prompt_parts.append(
        "Please summarize each article in Markdown format, following the structure and style shown above."
    )
    return "\n".join(prompt_parts)


async def _extract_and_crawl_links(
    base_url: str,
    markdown_content: str,
    llm_pool: LLMClientPool,
) -> Dict[str, Dict[str, str]]:
    """
    Extracts article links from Markdown using LLM and fetches sub-article content.
    Returns a mapping from sub-URL to its extracted metadata.
    """
    sub_original_content_metadata_dict: Dict[str, Dict[str, str]] = {}

    try:
        # 1) 请求LLM来识别相关链接
        link_prompt = build_link_extraction_prompt(base_url, markdown_content)
        links_str = await llm_pool.get_completion_content(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS},
                {"role": "user", "content": link_prompt},
            ],
            max_tokens=4096,
            temperature=0.0,
        )

        # 如果LLM没有返回链接，跳过而不报错
        if not links_str or not links_str.strip() or links_str.strip() == "no":
            logger.warning(
                f"No links found for {base_url}, skipping link extraction and crawling"
            )
            return sub_original_content_metadata_dict

        # 2) 过滤掉非URL链接、空链接和自引用链接
        extracted_links = []
        for link in links_str.splitlines():
            link = link.strip()
            if not link or link == base_url:
                continue

            # 规范化URL
            normalized_url = urljoin(base_url, link)

            # 检查URL是否有效（包含协议和域名）
            parsed_url = urlparse(normalized_url)
            if parsed_url.scheme and parsed_url.netloc:
                extracted_links.append(normalized_url)

        if not extracted_links:
            logger.warning(
                f"No valid links found for {base_url}, skipping link extraction and crawling"
            )
            return sub_original_content_metadata_dict

        # 3) 并发爬取每个提取的链接
        async with AiohttpCrawler() as sub_crawler:
            processed_count = 0
            total_links = len(extracted_links)

            async for crawl_result in sub_crawler.process_urls(
                extracted_links, max_retries=1
            ):
                processed_count += 1

                # 跳过任何失败的请求
                if crawl_result.get("error") or not crawl_result.get("content"):
                    continue

                sub_url = crawl_result.get(
                    "final_url", crawl_result.get("original_url")
                )
                if not sub_url:
                    continue

                # 从HTML中提取结构化数据（标题、日期、内容）
                structure_data = extract_metadata_from_article_html(
                    html_content=crawl_result["content"],
                    base_url=sub_url,
                )
                if not structure_data:
                    continue

                sub_original_content_metadata_dict[sub_url] = structure_data

    except Exception as e:
        logger.error(
            f"Error during link extraction and crawling for {base_url}: {e}",
            exc_info=True,
        )
        return sub_original_content_metadata_dict

    return sub_original_content_metadata_dict


async def summarize_content(
    url: str,
    original_content_metadata_dict: Dict[str, Dict[str, str]],
    llm_pool: LLMClientPool,
) -> List[Dict[str, str]]:
    """
    Args:
        url: The URL of the news.
        original_content_metadata_dict: A dictionary containing the original content metadata.
        llm_pool: The LLM pool to use for summarization.
        progress_callback: Optional callback for progress updates.

    Returns:
        A list of dictionaries containing the news summary.
        Each dictionary contains the following keys:
            - title: The title of the news.
            - url: The URL of the news.
            - date: The date of the news.
            - summary: The summary of the news.
            - content: The content of the news.
    """
    analysis_result: List[Dict[str, str]] = []

    analysis_prompt = build_content_analysis_prompt(original_content_metadata_dict)
    prompt_tokens = get_token_size(analysis_prompt)

    try:
        # If prompt size too large, split into smaller batches
        if prompt_tokens > llm_pool._context_window:
            num_prompt_chunks = (prompt_tokens // llm_pool._context_window) + 1

            chunk_maps: List[Dict[str, Dict[str, str]]] = []

            chunk_maps: List[Dict[str, Dict[str, str]]] = []
            keys = list(original_content_metadata_dict.keys())
            total = len(keys)

            if total < num_prompt_chunks:
                raise ValueError(
                    f"Token limit exceeded, not enough content to chunk for {url}."
                )

            size = total // num_prompt_chunks
            for i in range(num_prompt_chunks):
                start = i * size
                end = start + size if i < num_prompt_chunks - 1 else total
                part_keys = keys[start:end]
                if part_keys:
                    chunk_maps.append(
                        {k: original_content_metadata_dict[k] for k in part_keys}
                    )

            # Build separate prompts for each chunk
            prompt_chunks = [
                build_content_analysis_prompt(chunk_map) for chunk_map in chunk_maps
            ]
            logger.info(
                f"Analysis prompt chunking for {url}: {len(prompt_chunks)} parts."
            )

            # 处理每个分块
            for i, p_chunk in enumerate(prompt_chunks):
                llm_result = await llm_pool.get_completion_content(
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
                        },
                        {"role": "user", "content": p_chunk},
                    ],
                    max_tokens=llm_pool._max_tokens,
                    temperature=0.8,
                )
                # Parse JSON response
                try:
                    json_result = parse_json_from_text(llm_result)
                    analysis_result.extend(json_result)

                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON for {url}")
                except Exception as e:
                    logger.error(f"Failed to parse JSON for {url}: {e}")

        else:
            llm_result = await llm_pool.get_completion_content(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
                    },
                    {"role": "user", "content": analysis_prompt},
                ],
                max_tokens=llm_pool._max_tokens,
                temperature=0.8,
            )

            try:
                analysis_result = parse_json_from_text(llm_result)

            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON for {url}")
            except Exception as e:
                logger.error(f"Failed to parse JSON for {url}: {e}")

    except Exception as analyze_err:
        # Catch any analysis errors
        logger.error(f"LLM analysis failed for {url}: {analyze_err}", exc_info=True)

    # 添加原始内容到结果中，并移除没有URL的条目
    filtered_result = []
    for result_item in analysis_result:
        url_key = result_item.get("url", "")
        if url_key:
            result_item["date"] = original_content_metadata_dict.get(url_key, {}).get(
                "date", ""
            )
            result_item["content"] = original_content_metadata_dict.get(
                url_key, {}
            ).get("content", "")

            filtered_result.append(result_item)

    return filtered_result
