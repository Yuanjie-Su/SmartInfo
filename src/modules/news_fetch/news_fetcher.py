#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资讯获取模块 (Refactored)
负责协调资讯源的获取和保存
"""

import logging
import asyncio
from typing import List, Dict, Optional, Callable
import urllib.parse

# Import refactored components
from src.core.config import DEFAULT_DB_PATH
from src.database.operations import load_news_sources, save_news_item
from src.core.crawler import crawl_article

logger = logging.getLogger(__name__)


async def fetch_and_save_all(
    sources: Dict[str, Dict], on_item_saved: Optional[Callable] = None
) -> int:
    """
    获取指定资讯源列表的内容并保存到数据库

    Args:
        sources: 包含资讯源信息的字典列表。
                    每个字典应包含 'name', 'url', 'category'。
        on_item_saved: 可选的回调函数，每保存一个项目后调用，用于刷新界面。

    Returns:
        成功保存的新资讯数量
    """
    if not sources:  # 判断字典是否为空
        logger.warning("没有提供任何资讯源给fetch_and_save_all。")
        return 0

    urls = list(sources.keys())
    saved_items_count = 0

    async for result in crawl_article(urls):
        url = result["url"]
        articles = result["articles"]
        if len(articles) > 0:
            for article in articles:
                if "title" not in article or "link" not in article:
                    continue
                if save_news_item(
                    db_path=DEFAULT_DB_PATH,
                    title=str(article["title"]),
                    url=urllib.parse.urljoin(url, article["link"]),
                    source_name=sources[url]["name"],
                    category=sources[url]["category"],
                    summary=str(article.get("summary", "")),
                ):
                    saved_items_count += 1

            # 调用回调函数刷新界面
            if on_item_saved:
                on_item_saved()

    return saved_items_count


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
