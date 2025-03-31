#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import asyncio  # Added asyncio for LLM test
from typing import List, Dict, Optional
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


async def crawl_article(
    urls: List[str],
) -> Optional[List[Dict]]:
    """
    Crawls the given URLs to extract articles.

    Args:
        urls: The URLs to crawl.

    Returns:
        A list of dictionaries, each containing a URL and a list of articles,
        or None if crawling failed catastrophically.
    """
    logger.info(f"Attempting crawl for {len(urls)} URLs")
    if not urls or len(urls) == 0:
        return []

    # --- Browser and Dispatcher Configuration ---
    browser_conf = BrowserConfig(
        headless=True, viewport_width=1280, viewport_height=720
    )
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=80.0,
        check_interval=1.0,
        max_session_permit=10,
        rate_limiter=RateLimiter(base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2),
    )

    # --- CSS Extraction Schema ---
    css_schema = {
        "name": "Articles",
        "baseSelector": "article, .c-card, .teaser, .media, [role='article']",  # Added role=article
        "fields": [
            {
                "name": "title",
                "selector": "h1, h2, h3, h4, .title, .headline, .heading, .c-card__title, .article-item__title, .article__title, .post-title, .entry-title, .news-title, .story-title, .content-title, .article-title, .article-item__title-link, .article-item__title-link-text, .article-item__title-link-text-wrapper, .post__title, .card-title, .teaser-title, .media-heading, .item-title, a[aria-label*='title'], [class*='title'], [id*='title'], [itemprop='headline']",
                "type": "text",
            },
            {
                "name": "summary",
                "selector": "p, .summary, .description, .excerpt, .abstract, .intro, .subtitle, .desc, .c-card__summary, .article-item__summary, .article__summary, .post-summary, .entry-summary, .news-summary, .story-summary, .content-summary, .article-summary, .article-item__summary-text, .article-item__summary-text-wrapper, .post__summary, .card-text, .teaser-text, .media-body, .item-desc, [class*='summary'], [class*='description'], [class*='excerpt'], [id*='summary'], [itemprop='description']",
                "type": "text",
            },
            {
                "name": "link",
                "selector": "a, .link, .url, .href, .article-link, .post-link, .read-more, .more-link, .article-item__title-link, .article-item__title-link-text, .article-item__title-link-text-wrapper, .article-item__title-link-text-wrapper-text, h1 > a, h2 > a, h3 > a, h4 > a, .title > a, .headline > a, [class*='link'], [class*='url'], [id*='link'], [itemprop='url']",
                "type": "attribute",
                "attribute": "href",
            },
            {
                "name": "date",
                "selector": ".date, .time, .datetime, .published, .timestamp, .post-date, .article-date, .entry-date, .pub-date, time, [datetime], [class*='date'], [class*='time'], [id*='date'], [itemprop='datePublished'], [itemprop='dateModified']",
                "type": "text",
            },
        ],
    }
    css_extraction = JsonCssExtractionStrategy(css_schema)

    # --- crawl4ai Run Configuration ---
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=True,  # Process results as they come
        extraction_strategy=css_extraction,  # Use CSS strategy initially
        scan_full_page=True,
        exclude_external_links=True,
        remove_overlay_elements=True,
        process_iframes=False,  # Often less relevant for article extraction
        excluded_tags=[
            "form",
            "script",
            "style",
            "header",
            "footer",
            "nav",
            "aside",
            "menu",
        ],
    )

    results = []  # Store final results (url: str, articles: List[Dict])

    # --- Initial Crawl with CSS Strategy ---
    try:
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            async for result in await crawler.arun_many(
                urls=urls,
                config=run_conf,
                dispatcher=dispatcher,
            ):
                url_result = {"url": result.url, "articles": []}
                if result.success and result.extracted_content:
                    try:
                        articles = json.loads(result.extracted_content)
                        if (
                            isinstance(articles, list)
                            and len(articles) > 0
                            and all(isinstance(item, dict) for item in articles)
                        ):
                            logger.info(
                                f"CSS crawl successful for {result.url}. Found {len(articles)} items."
                            )
                            url_result["articles"] = articles
                        else:
                            logger.warning(
                                f"CSS crawl for {result.url} extracted non-standard list format. Type: {type(articles)}. Content: {str(articles)[:200]}"
                            )
                            url_result["articles"] = await crawl_article_with_llm(
                                url=result.url,
                                crawler=crawler,
                            )

                    except json.JSONDecodeError:
                        logger.warning(
                            f"CSS crawl for {result.url} returned non-JSON: {result.extracted_content[:200]}"
                        )
                        url_result["articles"] = await crawl_article_with_llm(
                            url=result.url,
                            crawler=crawler,
                        )
                    except Exception as parse_exc:
                        logger.error(
                            f"Error processing CSS result for {result.url}: {parse_exc}"
                        )
                        url_result["articles"] = await crawl_article_with_llm(
                            url=result.url,
                            crawler=crawler,
                        )
                elif result.success:
                    logger.info(
                        f"CSS crawl successful for {result.url}, but no content extracted."
                    )
                    url_result["articles"] = await crawl_article_with_llm(
                        url=result.url,
                        crawler=crawler,
                    )
                else:
                    logger.error(
                        f"CSS crawl failed for {result.url}: {result.error_message}"
                    )
                    url_result["articles"] = await crawl_article_with_llm(
                        url=result.url,
                        crawler=crawler,
                    )

                results.append(url_result)
    except Exception as e:
        logger.error(f"Exception during crawl article: {str(e)}", exc_info=True)
        # If initial crawl fails completely, maybe retry all with LLM?
        logger.warning("Crawl article failed.")

    return results


async def crawl_article_with_llm(url: str, crawler: AsyncWebCrawler):
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="deepseek/deepseek-chat",
            api_token="sk-32cadc805df8455a97b58fca20784c58",
        ),
        schema=model_json_schema(ArticleData),
        extraction_type="schema",
        instruction="Extract list of articles with 'title', 'summary', 'link', 'date' from the content.",
    )

    config = CrawlerRunConfig(
        exclude_external_links=True,
        word_count_threshold=10,
        extraction_strategy=llm_strategy,
    )

    result = await crawler.arun(url=url, config=config)
    if result.success and result.extracted_content:
        articles = json.loads(result.extracted_content)
        return articles
    else:
        return []
