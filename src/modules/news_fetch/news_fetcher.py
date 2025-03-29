#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资讯获取模块
负责从各类资讯源获取资讯内容
"""

import logging
import requests
import feedparser
from datetime import datetime
import sqlite3
import time
from typing import List, Dict, Any, Optional

from src.modules.news_parser.dynamic_parser import dynamic_parser

logger = logging.getLogger(__name__)


class NewsFetcher:
    """资讯获取器类"""

    def __init__(self, db_path: str):
        """
        初始化资讯获取器

        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = db_path
        self.sources = []
        self._load_sources()

    def _load_sources(self) -> None:
        """从数据库加载资讯源配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 更新查询，适应新的表结构
            cursor.execute("SELECT id, name, url, category FROM news_sources")
            sources = cursor.fetchall()

            self.sources = [
                {"id": src[0], "name": src[1], "url": src[2], "category": src[3]}
                for src in sources
            ]

            conn.close()
            logger.info(f"已加载 {len(self.sources)} 个资讯源")
        except Exception as e:
            logger.error(f"加载资讯源失败: {str(e)}", exc_info=True)
            # 如果数据库为空或出错，使用硬编码的默认资讯源
            self.sources = [
                {
                    "id": 1,
                    "name": "机器之心",
                    "url": "https://www.jiqizhixin.com/rss",
                    "category": "技术新闻",
                },
                {
                    "id": 2,
                    "name": "雷锋网AI频道",
                    "url": "https://www.leiphone.com/feed",
                    "category": "技术新闻",
                },
            ]
            logger.info("使用默认资讯源")

    def fetch_all(self, categories: Optional[List[str]] = None) -> int:
        """
        获取所有资讯源的内容

        Args:
            categories: 可选的分类过滤，None表示获取全部分类

        Returns:
            获取的资讯数量
        """
        total_fetched = 0

        for source in self.sources:
            # 如果指定了分类过滤，且当前源不在过滤范围内，则跳过
            if categories and source["category"] not in categories:
                continue

            logger.info(f"正在处理资讯源: {source['name']} ({source['url']})")

            fetched = self._fetch_with_dynamic_parser(source)

            total_fetched += fetched
            # 添加短暂延迟，避免频繁请求被封
            time.sleep(1)

        return total_fetched

    def _fetch_with_dynamic_parser(self, source: Dict[str, Any]) -> int:
        """
        使用动态解析器获取资讯

        Args:
            source: 资讯源配置

        Returns:
            获取的资讯数量
        """
        try:
            logger.info(f"正在使用动态解析器获取资讯源 {source['url']} 的内容")

            # 使用动态解析器解析内容
            parsed_items = dynamic_parser.parse_source(source["id"])

            if not parsed_items:
                logger.warning(f"资讯源 {source['name']} 未解析到内容")
                return 0

            # 保存解析结果
            count = 0
            for item in parsed_items:
                try:
                    # 确保必要字段存在
                    title = item.get("title", "无标题")
                    url = item.get("url", "")
                    content = item.get("content", "无内容")
                    publish_date = item.get(
                        "publish_date", datetime.now().strftime("%Y-%m-%d")
                    )

                    # 跳过没有URL的项目
                    if not url:
                        continue

                    # 保存到数据库
                    if self._save_news(
                        title,
                        url,
                        source["name"],
                        source["category"],
                        publish_date,
                        content,
                    ):
                        count += 1
                except Exception as e:
                    logger.error(f"保存解析项目失败: {str(e)}", exc_info=True)
                    continue

            logger.info(f"从资讯源 {source['name']} 更新了 {count} 条资讯")
            return count
        except Exception as e:
            logger.error(f"使用动态解析器获取资讯失败: {str(e)}", exc_info=True)
            return 0

    def _save_news(self, title, url, source, category, publish_date, content):
        """
        保存资讯到数据库

        Args:
            title: 资讯标题
            url: 资讯URL
            source: 资讯来源
            category: 资讯分类
            publish_date: 资讯发布日期
            content: 资讯内容

        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 检查资讯是否已存在
            cursor.execute("SELECT COUNT(*) FROM news WHERE url = ?", (url,))
            result = cursor.fetchone()

            if result[0] > 0:
                logger.info(f"资讯 {url} 已存在，跳过保存")
                return False

            # 保存资讯
            cursor.execute(
                """
            INSERT INTO news (title, url, source, category, publish_date, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
                (title, url, source, category, publish_date, content),
            )
            conn.commit()
            logger.info(f"保存资讯 {url} 成功")
            return True
        except Exception as e:
            logger.error(f"保存资讯失败: {str(e)}", exc_info=True)
            return False
