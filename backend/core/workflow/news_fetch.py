import json
import logging
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from utils.html_utils import (
    clean_and_format_html,
    extract_metadata_from_article_html,
)
from utils.markdown_utils import (
    clean_markdown_links,
    strip_javascript_links,
    strip_image_links,
)
from utils.parse import parse_json_from_text
from utils.prompt import (
    SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS,
    SYSTEM_PROMPT_EXTRACT_SUMMARIZE_ARTICLE_BATCH,
)
from utils.text_utils import get_chunks
from utils.token_utils import get_token_size
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
    start_time = time.time()
    logger.info(f"开始处理URL: {url}")
    
    # 报告开始进行爬取操作
    if progress_callback:
        await progress_callback("crawling", 10, f"正在爬取页面: {url}")

    # 1) Crawl html content (contains news content and links to other pages) from url
    # and format it to cleaned markdown
    crawler_result = None
    logger.info(f"使用Selenium爬虫开始爬取: {url}")
    try:
        async with SeleniumCrawler() as crawler:
            crawler_result = await crawler.fetch_single(url)
            logger.info(f"Selenium爬虫爬取完成: {url}")
    except Exception as e:
        logger.error(f"Selenium爬虫爬取失败: {url}, 错误: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to crawl {url}: {str(e)}")

    if not crawler_result or crawler_result.get("error"):
        error_msg = crawler_result.get("error", "未知错误") if crawler_result else "空结果"
        logger.error(f"爬取结果包含错误: {url}, 错误: {error_msg}")
        raise ValueError(f"Failed to crawl {url}: {error_msg}")

    html_content = crawler_result.get("content", "")
    html_length = len(html_content) if html_content else 0
    logger.info(f"获取到HTML内容: {url}, 内容长度: {html_length}字节")
    
    if not html_content:
        logger.error(f"爬取到的HTML内容为空: {url}")
        raise ValueError(f"Failed to crawl {url}")

    logger.info(f"开始清理HTML并转换为Markdown: {url}")
    cleaned_markdown = _clean_and_prepare_markdown(
        url=url, html_content=html_content, exclude_links=exclude_links
    )

    markdown_length = len(cleaned_markdown) if cleaned_markdown else 0
    logger.info(f"HTML清理完成: {url}, Markdown长度: {markdown_length}字节")
    
    if not cleaned_markdown:
        logger.error(f"HTML清理失败: {url}")
        raise ValueError("Failed to clean and prepare markdown")

    # 2) Extract links from the cleaned markdown
    if progress_callback:
        await progress_callback("extracting", 20, "正在从页面提取文章链接")

    # 2a) Evaluate token size and chunk if exceeding context window
    token_size = get_token_size(cleaned_markdown)
    logger.info(f"Markdown Token计数: {url}, 共{token_size}个token")
    
    markdown_chunks = [cleaned_markdown]
    num_chunks = 1
    if token_size > llm_pool._context_window:
        num_chunks = (token_size // llm_pool._context_window) + 1
        logger.info(f"内容超出上下文窗口大小, 需要分块: {url}, 分为{num_chunks}块")
        
        if progress_callback:
            await progress_callback(
                "chunking", 25, f"页面内容较大，正在分割为 {num_chunks} 个部分进行处理"
            )
        try:
            # Split long Markdown into line-based chunks
            logger.info(f"开始执行内容分块: {url}")
            markdown_chunks = get_chunks(cleaned_markdown, num_chunks)
            logger.info(f"内容分块完成: {url}, 实际生成了{len(markdown_chunks)}个块")
        except Exception as e:
            # Fallback to single chunk on error
            logger.error(f"内容分块失败: {url}, 错误: {str(e)}", exc_info=True)
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
    logger.info(f"准备处理{chunk_count}个内容块: {url}")
    
    for i, chunk_content in enumerate(markdown_chunks):
        if not chunk_content.strip():
            logger.warning(f"跳过空块: {url}, 块索引: {i+1}/{chunk_count}")
            continue

        logger.info(f"开始处理内容块 {i+1}/{chunk_count}: {url}, 块大小: {len(chunk_content)}字节")
        
        if progress_callback and chunk_count > 1:
            await progress_callback(
                "processing",
                30 + (i * 10 / chunk_count),
                f"正在处理页面分块 {i+1}/{chunk_count}",
            )

        # Link extraction and crawling
        logger.info(f"开始提取和爬取链接: {url}, 块 {i+1}/{chunk_count}")
        sub_original_content_metadata_dict = await _extract_and_crawl_links(
            url, chunk_content, llm_pool
        )

        if not sub_original_content_metadata_dict:
            # Skip analysis if no sub-articles found
            logger.warning(f"块中未找到有效链接: {url}, 块 {i+1}/{chunk_count}")
            continue

        # Add each link and its metadata to the main dictionary
        found_count = len(sub_original_content_metadata_dict)
        logger.info(f"在块 {i+1}/{chunk_count} 中找到 {found_count} 个有效链接: {url}")
        original_content_metadata_dict.update(sub_original_content_metadata_dict)

    total_articles = len(original_content_metadata_dict)
    logger.info(f"全部块处理完成, 总共找到 {total_articles} 篇文章: {url}")
    
    if not original_content_metadata_dict:
        logger.error(f"未找到任何有效内容: {url}")
        raise ValueError("No original content metadata found")

    # 报告即将进行内容总结
    if progress_callback:
        await progress_callback(
            "analyzing",
            60,
            f"找到 {len(original_content_metadata_dict)} 个文章，正在进行分析和总结",
        )

    # 3) Summarize the original content
    logger.info(f"开始对 {total_articles} 篇文章进行摘要处理: {url}")
    summary_result = await summarize_content(
        url=url,
        original_content_metadata_dict=original_content_metadata_dict,
        llm_pool=llm_pool,
    )

    summary_count = len(summary_result) if summary_result else 0
    logger.info(f"摘要处理完成, 成功处理了 {summary_count} 篇文章: {url}")
    
    if not summary_result:
        logger.error(f"摘要处理失败或结果为空: {url}")
        raise ValueError("Failed to summarize the original content")

    # 报告完成
    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.info(f"完成处理URL: {url}, 耗时: {elapsed_time:.2f}秒, 处理了 {summary_count} 篇文章")
    
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
    logger.debug(f"开始清理HTML内容: {url}, HTML长度: {len(html_content)}字节")
    try:
        # Convert HTML to markdown
        logger.debug(f"转换HTML为Markdown: {url}")
        cleaned_markdown = clean_and_format_html(
            html_content=html_content,
            base_url=url,
            output_format="markdown",
        )
        logger.debug(f"HTML转换完成, Markdown长度: {len(cleaned_markdown)}字节")

        logger.debug(f"删除图片链接: {url}")
        cleaned_markdown = strip_image_links(cleaned_markdown)

        logger.debug(f"删除JavaScript链接: {url}")
        cleaned_markdown = strip_javascript_links(cleaned_markdown)

        # # Remove or adjust any residual markdown links
        # cleaned_markdown = clean_markdown_links(
        #     markdown, exclude_urls=exclude_links, base_url=url
        # )

        logger.debug(f"HTML清理完成: {url}")
        return cleaned_markdown
    except Exception as e:
        logger.error(
            f"HTML清理/格式化过程中发生错误: {url}: {e}", exc_info=True
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
    logger.debug(f"构建链接提取提示词, 长度: {len(prompt)}字节")
    return prompt


def build_content_analysis_prompt(
    original_content_metadata_dict: Dict[str, Dict[str, str]],
) -> str:
    """Build the prompt containing article metadata to guide LLM summarization."""
    if not original_content_metadata_dict:
        logger.warning("没有提供文章元数据，无法构建内容分析提示词")
        return ""

    prompt_parts: List[str] = []
    article_count = len(original_content_metadata_dict)
    logger.debug(f"构建内容分析提示词, 共 {article_count} 篇文章")
    
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
    prompt = "\n".join(prompt_parts)
    logger.debug(f"内容分析提示词构建完成, 长度: {len(prompt)}字节")
    return prompt


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
    logger.debug(f"开始从Markdown中提取链接: {base_url}, Markdown长度: {len(markdown_content)}字节")

    try:
        # 1) 请求LLM来识别相关链接
        logger.debug(f"构建LLM提取链接的提示词: {base_url}")
        link_prompt = build_link_extraction_prompt(base_url, markdown_content)
        
        logger.info(f"请求LLM识别页面中的文章链接: {base_url}")
        links_str = await llm_pool.get_completion_content(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACT_ARTICLE_LINKS},
                {"role": "user", "content": link_prompt},
            ],
            max_tokens=4096,
            temperature=0.0,
        )
        logger.debug(f"LLM返回的链接原始结果, 长度: {len(links_str) if links_str else 0}字节")

        # 如果LLM没有返回链接，跳过而不报错
        if not links_str or not links_str.strip() or links_str.strip() == "no":
            logger.warning(
                f"LLM未发现链接: {base_url}, 跳过链接提取和爬取"
            )
            return sub_original_content_metadata_dict

        # 2) 过滤掉非URL链接、空链接和自引用链接
        logger.debug(f"开始处理和规范化LLM提取的链接: {base_url}")
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
                logger.debug(f"提取有效链接: {normalized_url}")
            else:
                logger.debug(f"忽略无效链接: {link} -> {normalized_url}")

        if not extracted_links:
            logger.warning(
                f"未找到有效链接: {base_url}, 跳过链接提取和爬取"
            )
            return sub_original_content_metadata_dict

        logger.info(f"找到 {len(extracted_links)} 个有效链接, 开始爬取: {base_url}")
        
        # 3) 并发爬取每个提取的链接
        async with AiohttpCrawler() as sub_crawler:
            processed_count = 0
            total_links = len(extracted_links)

            async for crawl_result in sub_crawler.process_urls(
                extracted_links, max_retries=1
            ):
                processed_count += 1
                logger.debug(f"爬取进度: {processed_count}/{total_links} ({processed_count*100/total_links:.1f}%)")

                # 跳过任何失败的请求
                if crawl_result.get("error") or not crawl_result.get("content"):
                    error_msg = crawl_result.get("error", "内容为空")
                    orig_url = crawl_result.get("original_url", "未知URL")
                    logger.warning(f"子链接爬取失败: {orig_url}, 错误: {error_msg}")
                    continue

                sub_url = crawl_result.get(
                    "final_url", crawl_result.get("original_url")
                )
                if not sub_url:
                    logger.warning("爬取结果中缺少URL信息，跳过此结果")
                    continue

                # 从HTML中提取结构化数据（标题、日期、内容）
                logger.debug(f"从HTML中提取元数据: {sub_url}")
                structure_data = extract_metadata_from_article_html(
                    html_content=crawl_result["content"],
                    base_url=sub_url,
                )
                if not structure_data:
                    logger.warning(f"无法从HTML中提取元数据: {sub_url}")
                    continue

                title = structure_data.get("title", "无标题")
                content_length = len(structure_data.get("content", ""))
                logger.info(f"成功提取文章: {sub_url}, 标题: {title}, 内容长度: {content_length}字节")
                sub_original_content_metadata_dict[sub_url] = structure_data

        logger.info(f"子链接爬取完成: {base_url}, 成功爬取 {len(sub_original_content_metadata_dict)}/{total_links} 个子链接")

    except Exception as e:
        logger.error(
            f"链接提取和爬取过程中发生错误: {base_url}: {e}",
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
    article_count = len(original_content_metadata_dict)
    logger.info(f"开始内容摘要处理: {url}, 文章数量: {article_count}")

    analysis_prompt = build_content_analysis_prompt(original_content_metadata_dict)
    prompt_tokens = get_token_size(analysis_prompt)
    logger.info(f"内容分析提示词Token数量: {prompt_tokens}")

    try:
        # If prompt size too large, split into smaller batches
        if prompt_tokens > llm_pool._context_window:
            logger.info(f"提示词超过上下文窗口限制 ({prompt_tokens} > {llm_pool._context_window}), 需要分块处理")
            num_prompt_chunks = (prompt_tokens // llm_pool._context_window) + 1
            logger.info(f"计划分为 {num_prompt_chunks} 个块进行处理")

            chunk_maps: List[Dict[str, Dict[str, str]]] = []
            keys = list(original_content_metadata_dict.keys())
            total = len(keys)

            if total < num_prompt_chunks:
                logger.error(f"Token数量超限，但文章数量 ({total}) 少于分块数量 ({num_prompt_chunks}), 无法有效分块")
                raise ValueError(
                    f"Token limit exceeded, not enough content to chunk for {url}."
                )

            logger.info(f"每个块将包含约 {total // num_prompt_chunks} 篇文章")
            size = total // num_prompt_chunks
            for i in range(num_prompt_chunks):
                start = i * size
                end = start + size if i < num_prompt_chunks - 1 else total
                part_keys = keys[start:end]
                if part_keys:
                    chunk_maps.append(
                        {k: original_content_metadata_dict[k] for k in part_keys}
                    )
                    logger.debug(f"块 {i+1} 包含 {len(part_keys)} 篇文章, 从索引 {start} 到 {end-1}")

            # Build separate prompts for each chunk
            prompt_chunks = [
                build_content_analysis_prompt(chunk_map) for chunk_map in chunk_maps
            ]
            logger.info(
                f"已创建 {len(prompt_chunks)} 个提示词块, 准备分批处理: {url}"
            )

            # 处理每个分块
            for i, p_chunk in enumerate(prompt_chunks):
                logger.info(f"开始处理提示词块 {i+1}/{len(prompt_chunks)}")
                chunk_token_size = get_token_size(p_chunk)
                logger.info(f"块 {i+1} 的Token数量: {chunk_token_size}")
                
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
                logger.debug(f"块 {i+1} LLM返回结果长度: {len(llm_result)}字节")
                
                # Parse JSON response
                try:
                    json_result = parse_json_from_text(llm_result)
                    result_count = len(json_result) if json_result else 0
                    logger.info(f"成功从块 {i+1} 解析出 {result_count} 篇文章摘要")
                    analysis_result.extend(json_result)

                except json.JSONDecodeError as je:
                    logger.error(f"块 {i+1} JSON解析失败: {url}, 错误位置: {str(je)}")
                    logger.debug(f"JSON解析失败的原始内容: {llm_result[:500]}...")
                except Exception as e:
                    logger.error(f"块 {i+1} 处理过程中发生错误: {url}: {e}", exc_info=True)

        else:
            logger.info(f"提示词在Token限制内，进行单次处理: {url}")
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
            logger.debug(f"LLM返回结果长度: {len(llm_result)}字节")

            try:
                analysis_result = parse_json_from_text(llm_result)
                result_count = len(analysis_result) if analysis_result else 0
                logger.info(f"成功解析出 {result_count} 篇文章摘要")

            except json.JSONDecodeError as je:
                logger.error(f"JSON解析失败: {url}, 错误位置: {str(je)}")
                logger.debug(f"JSON解析失败的原始内容: {llm_result[:500]}...")
            except Exception as e:
                logger.error(f"处理过程中发生错误: {url}: {e}", exc_info=True)

    except Exception as analyze_err:
        # Catch any analysis errors
        logger.error(f"LLM分析过程中发生错误: {url}: {analyze_err}", exc_info=True)

    # 添加原始内容到结果中，并移除没有URL的条目
    logger.info(f"开始处理最终结果，当前有 {len(analysis_result)} 篇文章摘要")
    filtered_result = []
    missing_url_count = 0
    
    for result_item in analysis_result:
        url_key = result_item.get("url", "")
        if url_key:
            # 添加原始日期和内容
            result_item["date"] = original_content_metadata_dict.get(url_key, {}).get(
                "date", ""
            )
            result_item["content"] = original_content_metadata_dict.get(
                url_key, {}
            ).get("content", "")
            
            title = result_item.get("title", "无标题")
            summary_length = len(result_item.get("summary", ""))
            logger.debug(f"添加文章到最终结果: {url_key}, 标题: {title}, 摘要长度: {summary_length}字节")
            filtered_result.append(result_item)
        else:
            missing_url_count += 1
            logger.warning(f"忽略缺少URL的结果项: {result_item.get('title', '无标题')}")

    logger.info(f"最终结果处理完成: {url}, 共 {len(filtered_result)} 篇有效文章, 忽略了 {missing_url_count} 篇无URL文章")
    return filtered_result
