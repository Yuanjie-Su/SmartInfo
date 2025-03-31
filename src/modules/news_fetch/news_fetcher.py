#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资讯获取模块 (Refactored)
负责协调资讯源的获取和保存
"""

import logging
import asyncio
from typing import List, Dict, Optional
import urllib.parse

# Import refactored components
from src.core.config import DEFAULT_DB_PATH
from src.database.operations import load_news_sources, save_news_item
from src.core.crawler import crawl_article

logger = logging.getLogger(__name__)


async def fetch_and_save_all(sources: List[Dict]) -> int:
    """
    获取指定资讯源列表的内容并保存到数据库

    Args:
        sources: 包含资讯源信息的字典列表。
                    每个字典应包含 'name', 'url', 'category'。

    Returns:
        成功保存的新资讯数量
    """
    if len(sources) == 0:
        logger.warning("No sources provided to fetch_and_save_all.")
        return 0

    urls = [source["url"] for source in sources]
    results = await crawl_article(urls)
    # 处理results
    saved_items_count = 0
    for result in results:
        url = result["url"]
        articles = result["articles"]
        if len(articles) > 0:
            for article in articles:
                if save_news_item(
                    db_path=DEFAULT_DB_PATH,
                    title=str(article["title"]),
                    url=urllib.parse.urljoin(url, article["link"]),
                    source_name=next(s["name"] for s in sources if s["url"] == url),
                    category=next(s["category"] for s in sources if s["url"] == url),
                    publish_date=str(article["date"]) if article["date"] else None,
                    summary=str(article["summary"]),
                    content=str(article.get("content", "")),
                ):
                    saved_items_count += 1


# Example usage (for testing - requires manual source list)
async def main():
    logging.basicConfig(level=logging.INFO)
    # Example sources - replace with actual sources needed for testing
    test_sources = [
        {
            "name": "机器之心 Test",
            "url": "https://www.jiqizhixin.com/rss",
            "category": "Tech",
        },
        # Add more test sources if needed
    ]
    print(f"Fetching from {len(test_sources)} sources...")
    saved_count = await fetch_and_save_all(test_sources)
    print(f"Total new news items saved: {saved_count}")


if __name__ == "__main__":
    # Ensure you have an event loop running if testing directly
    # asyncio.run(main())
    pass
