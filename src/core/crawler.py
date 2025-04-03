#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import asyncio
from typing import List, Dict, Optional, AsyncGenerator, Any
from pydantic.json_schema import model_json_schema
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    RateLimiter,
    CacheMode,
    LLMConfig,
)
from crawl4ai.extraction_strategy import (
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
)
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher

from src.models.news import ArticleData

logger = logging.getLogger(__name__)


def _create_browser_config() -> BrowserConfig:
    """
    创建浏览器配置

    Returns:
        BrowserConfig: 浏览器配置对象
    """
    return BrowserConfig(headless=True, viewport_width=1280, viewport_height=720)


def _create_dispatcher() -> MemoryAdaptiveDispatcher:
    """
    创建内存自适应调度器

    Returns:
        MemoryAdaptiveDispatcher: 调度器对象
    """
    return MemoryAdaptiveDispatcher(
        memory_threshold_percent=90.0,
        check_interval=1.0,
        max_session_permit=10,
        rate_limiter=RateLimiter(base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2),
    )


def _create_css_extraction_strategy() -> JsonCssExtractionStrategy:
    """
    创建基于CSS选择器的提取策略

    Returns:
        JsonCssExtractionStrategy: CSS提取策略对象
    """
    css_schema = {
        "name": "Articles",
        "baseSelector": "article, .c-card, .teaser, .media, [role='article'], .post, .news-item, .blog-item, .content-item, .article-block, .entry, .story, .article-container, .article-wrapper, .media-article, .post-preview, .item-article",
        "fields": [
            {
                "name": "title",
                "selector": (
                    "h1, h2, h3, h4, "
                    ".title, .headline, .heading, .c-card__title, .article-item__title, "
                    ".article__title, .post-title, .entry-title, .news-title, .story-title, "
                    ".content-title, .article-title, .article-item__title-link, "
                    ".article-item__title-link-text, .article-item__title-link-text-wrapper, "
                    ".post__title, .card-title, .teaser-title, .media-heading, .item-title, "
                    ".blog-title, .news-headline, .main-title, .top-title, "
                    "a[aria-label*='title'], [class*='title'], [id*='title'], "
                    "[itemprop='headline'], [class*='headline'], [class*='heading']"
                ),
                "type": "text",
            },
            # {
            #     "name": "summary",
            #     "selector": (
            #         "p, .summary, .description, .excerpt, .abstract, .intro, .subtitle, .desc, "
            #         ".c-card__summary, .article-item__summary, .article__summary, .post-summary, "
            #         ".entry-summary, .news-summary, .story-summary, .content-summary, "
            #         ".article-summary, .article-item__summary-text, "
            #         ".article-item__summary-text-wrapper, .post__summary, .card-text, "
            #         ".teaser-text, .media-body, .item-desc, .lead, .synopsis, .overview, "
            #         "[class*='summary'], [class*='description'], [class*='excerpt'], "
            #         "[class*='abstract'], [id*='summary'], [itemprop='description']"
            #     ),
            #     "type": "text",
            # },
            {
                "name": "link",
                "selector": (
                    "a, .link, .url, .href, .article-link, .post-link, .read-more, .more-link, "
                    ".article-item__title-link, .article-item__title-link-text, "
                    ".article-item__title-link-text-wrapper, "
                    ".article-item__title-link-text-wrapper-text, h1 > a, h2 > a, h3 > a, h4 > a, "
                    ".title > a, .headline > a, .entry-title > a, .story-title > a, "
                    "[class*='link'], [class*='url'], [id*='link'], [itemprop='url'], "
                    "[href*='article'], [href*='story'], [href*='news'], [href*='post']"
                ),
                "type": "attribute",
                "attribute": "href",
            },
            {
                "name": "date",
                "selector": (
                    ".date, .time, .datetime, .published, .timestamp, .post-date, .article-date, "
                    ".entry-date, .pub-date, time, .meta-time, .timeago, .publish-date, "
                    "[datetime], [class*='date'], [class*='time'], [id*='date'], "
                    "[itemprop='datePublished'], [itemprop='dateModified'], "
                    "time[datetime], .date-posted, .posted-on, .byline-time"
                ),
                "type": "text",
            },
        ],
    }

    return JsonCssExtractionStrategy(css_schema)


def _create_llm_extraction_strategy() -> LLMExtractionStrategy:
    """
    创建基于LLM的提取策略

    Returns:
        LLMExtractionStrategy: LLM提取策略对象
    """
    return LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="deepseek/deepseek-chat",
            api_token="sk-32cadc805df8455a97b58fca20784c58",
            temprature=0.0,
        ),
        schema=model_json_schema(ArticleData),
        extraction_type="schema",
        instruction="Extract list of articles with 'title', 'link', 'date' from the html_content.",
    )


def _create_run_config(extraction_strategy: Any) -> CrawlerRunConfig:
    """
    创建爬虫运行配置

    Args:
        extraction_strategy: 提取策略对象

    Returns:
        CrawlerRunConfig: 爬虫运行配置对象
    """
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=True,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,
        exclude_external_links=True,
        remove_overlay_elements=True,
        process_iframes=False,
        excluded_tags=[
            "form",
            "script",
            "style",
            "header",
            "footer",
            "nav",
            "aside",
            "noscript",  # 不被渲染的备用内容
            "iframe",  # 通常嵌套外部内容（已通过 process_iframes 处理）
            "canvas",  # 图形绘制，不含文本
            "svg",  # 矢量图
            "figure",  # 图片/图表组合区域
            "figcaption",  # 图表说明
            "video",
            "audio",  # 媒体播放区域
            "object",
            "embed",  # 插件或外部嵌入
            "meta",
            "base",  # 页面元信息
            "input",
            "button",
            "select",
            "textarea",  # 表单输入元素
            "picture",  # 响应式图片容器
            "track",
            "source",  # 媒体源
            "label",  # 表单标签
        ],
    )


async def _process_css_crawl_results(
    crawler: AsyncWebCrawler,
    urls: List[str],
    dispatcher: MemoryAdaptiveDispatcher,
    run_conf: CrawlerRunConfig,
) -> AsyncGenerator[Dict, None]:
    """
    使用CSS选择器策略处理爬取结果

    Args:
        crawler: 爬虫对象
        urls: 要爬取的URL列表
        dispatcher: 调度器
        run_conf: 运行配置

    Yields:
        爬取的结果
    """

    async for result in await crawler.arun_many(
        urls=urls,
        config=run_conf,
        dispatcher=dispatcher,
    ):
        url_result = {"url": result.url, "articles": []}

        if result.success and result.extracted_content:
            try:
                articles = json.loads(result.extracted_content)
                if isinstance(articles, list):
                    if len(articles) > 0:
                        logger.info(
                            f"CSS爬取成功: {result.url}。找到 {len(articles)} 个项目。"
                        )
                        url_result["articles"] = articles
                    else:
                        logger.warning(
                            f"CSS爬取 {result.url} 提取到空列表。转用LLM策略。"
                        )
                else:
                    logger.warning(
                        f"CSS爬取 {result.url} 提取到非标准列表格式。类型: {type(articles)}。转用LLM策略。内容: {str(articles)[:200]}"
                    )
            except json.JSONDecodeError:
                logger.warning(
                    f"CSS爬取 {result.url} 返回非JSON内容。转用LLM策略。内容: {result.extracted_content[:200]}"
                )
            except Exception as parse_exc:
                logger.error(
                    f"处理 {result.url} 的CSS结果时出错: {parse_exc}。转用LLM策略。"
                )
        elif result.success:
            logger.info(f"CSS爬取 {result.url} 成功，但未提取到内容。转用LLM策略。")
        else:
            logger.error(
                f"CSS爬取 {result.url} 失败: {result.error_message}。转用LLM策略。"
            )

        yield url_result


async def _process_llm_crawl_results(
    crawler: AsyncWebCrawler,
    urls_llm: List[str],
    dispatcher: MemoryAdaptiveDispatcher,
    run_conf: CrawlerRunConfig,
) -> AsyncGenerator[Dict, None]:
    """
    使用LLM策略处理爬取结果

    Args:
        crawler: 爬虫对象
        urls_llm: 要爬取的URL列表
        dispatcher: 调度器
        run_conf: 运行配置

    Yields:
        爬取结果
    """
    if not urls_llm:
        return

    logger.info(f"等待 {len(urls_llm)} 个LLM后备任务完成...")

    async for result in await crawler.arun_many(
        urls=urls_llm,
        config=run_conf,
        dispatcher=dispatcher,
    ):
        if result.success and result.extracted_content:
            articles = json.loads(result.extracted_content)
            yield {"url": result.url, "articles": articles}
        else:
            yield {"url": result.url, "articles": []}


async def crawl_article(
    urls: List[str],
) -> AsyncGenerator[Dict, None]:
    """
    爬取给定URL以提取文章，并逐步生成结果。

    Args:
        urls: 要爬取的URL列表

    Yields:
        包含URL和提取的文章的字典
    """
    logger.info(f"尝试爬取 {len(urls)} 个URL")
    if not urls or len(urls) == 0:
        return

    # --- 创建浏览器和调度器配置 ---
    browser_conf = _create_browser_config()
    dispatcher = _create_dispatcher()

    # --- 创建CSS提取策略 ---
    css_extraction = _create_css_extraction_strategy()

    # --- 创建爬虫运行配置(CSS策略) ---
    css_run_conf = _create_run_config(css_extraction)

    # 初始化爬虫
    crawler = AsyncWebCrawler(config=browser_conf)
    await crawler.start()

    try:
        # --- 使用CSS策略进行初始爬取 ---
        urls_llm = []
        # 处理CSS爬取结果
        css_generator = _process_css_crawl_results(
            crawler, urls, dispatcher, css_run_conf
        )

        # 收集所有CSS爬取结果并将其传递给调用者
        async for result in css_generator:
            if result["articles"] == []:
                urls_llm.append(result["url"])
            else:
                yield result

        # --- 对失败的URL使用LLM策略进行后备爬取 ---
        if urls_llm:
            # 创建LLM提取策略
            llm_strategy = _create_llm_extraction_strategy()

            # 创建LLM爬虫运行配置
            llm_run_conf = _create_run_config(llm_strategy)

            # 处理LLM爬取结果
            async for result in _process_llm_crawl_results(
                crawler, urls_llm, dispatcher, llm_run_conf
            ):
                yield result

    except Exception as e:
        logger.error(f"爬取文章时发生异常: {str(e)}", exc_info=True)
        logger.warning("爬取文章失败。")

    # 关闭爬虫
    await crawler.close()
