#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import asyncio
import re
from typing import List, Dict, Optional, AsyncGenerator, Any
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    RateLimiter,
    CacheMode,
)
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher

logger = logging.getLogger(__name__)


def _create_browser_config() -> BrowserConfig:
    """
    Create browser configuration

    Returns:
        BrowserConfig: Browser configuration object
    """
    return BrowserConfig(headless=True, viewport_width=1280, viewport_height=720)


def _create_dispatcher() -> MemoryAdaptiveDispatcher:
    """
    Create memory adaptive dispatcher

    Returns:
        MemoryAdaptiveDispatcher: Dispatcher object
    """
    return MemoryAdaptiveDispatcher(
        memory_threshold_percent=90.0,
        check_interval=1.0,
        max_session_permit=10,
        rate_limiter=RateLimiter(base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2),
    )


def _create_run_config(extraction_strategy=None) -> CrawlerRunConfig:
    """
    Create crawler run configuration

    Args:
        extraction_strategy: Extraction strategy object

    Returns:
        CrawlerRunConfig: Crawler run configuration object
    """
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=True,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,
        exclude_external_links=True,
        exclude_external_images=True,
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
            "noscript",
            "canvas",
            "svg",
            "figure",
            "figcaption",
            "video",
            "audio",
            "object",
            "embed",
            "meta",
            "base",
            "input",
            "button",
            "select",
            "textarea",
            "picture",
            "track",
            "source",
            "label",
            "iframe",
            "link",
        ],
        excluded_selector=(
            ".ad, .ads, .advert, .back-to-top, .conditions, .contribute, "
            ".disclaimer, .editor-choice, .follow, .join-community, .menu, "
            ".navigation, .popup, .post-article, .privacy, .read-more, "
            ".recommended, .related-articles, .report, .repost, .see-more, "
            ".share, .share-bar, .sponsored, .subscribe, .submit, .terms, "
            ".top, .top-picks, .top-stories, .trending, .unfollow, .view-details, "
            ".write-article, aside, audio, base, button, canvas, figcaption, "
            "figure, footer, header, iframe, img, input, label, meta, nav, "
            "noscript, picture, script, select, source, style, svg, textarea, "
            "track, video"
        ),
    )


async def process_crawl_results(
    crawler: AsyncWebCrawler,
    urls: List[str],
    dispatcher: MemoryAdaptiveDispatcher,
    run_conf: CrawlerRunConfig,
) -> AsyncGenerator[Dict, None]:
    """
    Process crawl results
    """
    logger.info(f"Waiting for {len(urls)} crawl tasks to complete...")

    async for result in await crawler.arun_many(
        urls=urls,
        config=run_conf,
        dispatcher=dispatcher,
    ):
        if result.success and result.markdown:
            yield {"url": result.url, "markdown": result.markdown}
        else:
            yield {"url": result.url, "markdown": ""}


async def get_markdown_by_url(urls: List[str]) -> AsyncGenerator[Dict, None]:
    """
    Crawl given URLs to extract markdown content and yield results incrementally.

    Args:
        urls: List of URLs to crawl

    Yields:
        Dictionary containing URL and extracted markdown content
    """
    logger.info(f"Attempting to crawl {len(urls)} URLs")
    if not urls or len(urls) == 0:
        return

    # --- Create browser and dispatcher configuration ---
    browser_conf = _create_browser_config()
    dispatcher = _create_dispatcher()

    # --- Create crawler run configuration ---
    run_conf = _create_run_config()

    # Initialize crawler
    crawler = AsyncWebCrawler(config=browser_conf)
    await crawler.start()

    try:
        generator = process_crawl_results(crawler, urls, dispatcher, run_conf)

        # Collect all crawl results and yield to caller
        async for result in generator:
            if result["markdown"]:
                yield {
                    "url": result["url"],
                    # "markdown": filter_markdown_content(result["markdown"]),
                    "markdown": result["markdown"],
                }
            else:
                yield {"url": result["url"], "markdown": ""}
    except Exception as e:
        logger.error(
            f"An exception occurred while crawling articles: {str(e)}", exc_info=True
        )
        logger.warning("Failed to crawl articles.")

    # Close crawler
    await crawler.close()


def filter_markdown_content(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    result = []

    invalid_keywords = [
        # Chinese keywords (navigation, operations, platform-related)
        "登录",
        "注册",
        "消息",
        "创作",
        "首页",
        "会员",
        "排行榜",
        "点赞",
        "收藏",
        "评论",
        "下载",
        "一键运行",
        "查看详情",
        "更多",
        "广告",
        "导航",
        "写文章",
        "加入社区",
        "推荐",
        "头条",
        "热榜",
        "分享",
        "转发",
        "声明",
        "免责声明",
        "编辑",
        "置顶",
        "举报",
        "关注",
        "回复",
        "相关推荐",
        "我要投稿",
        "欢迎投稿",
        # English keywords (UI elements, promotions, non-content buttons)
        "login",
        "sign in",
        "sign up",
        "register",
        "message",
        "inbox",
        "home",
        "dashboard",
        "subscribe",
        "membership",
        "ranking",
        "like",
        "comment",
        "download",
        "run now",
        "details",
        "more",
        "ad",
        "ads",
        "sponsored",
        "navigation",
        "menu",
        "top",
        "top stories",
        "top picks",
        "editor's choice",
        "recommended",
        "related articles",
        "read more",
        "see more",
        "view details",
        "back to top",
        "write article",
        "post article",
        "join community",
        "share",
        "repost",
        "submit",
        "contribute",
        "trending",
        "follow",
        "unfollow",
        "report",
        "disclaimer",
        "privacy",
        "terms",
        "conditions",
    ]

    for i, line in enumerate(lines):
        # Find all markdown links
        links = re.findall(r"\[([^\[\]]+)\]\((https?://[^\)]+)\)", line)
        if not links:
            continue

        # Remove titles that are empty or contain invalid keywords
        filtered_links = [
            (title.strip(), url)
            for title, url in links
            if title.strip() and not any(kw in title for kw in invalid_keywords)
        ]
        if not filtered_links:
            continue

        # Remove duplicate URLs, keeping only the first occurrence
        seen_urls = set()
        dedup_links = []
        for title, url in filtered_links:
            if url not in seen_urls:
                seen_urls.add(url)
                dedup_links.append((title, url))
            else:
                dedup_links.append((title, None))  # Remove link but keep title

        # Construct a new line
        reconstructed = []
        for title, url in dedup_links:
            if url:
                reconstructed.append(f"[{title}]({url})")
            else:
                reconstructed.append(f"[{title}]")  # Link removed, keep only text title

        new_line = " ".join(reconstructed)

        result.append(new_line)

    return "\n".join(result)
