#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
动态网页内容解析器
负责动态解析网页内容，从数据库获取解析代码并执行
"""

import logging
import sqlite3
import importlib.util
import sys
import tempfile
import os
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from src.modules.news_parser.test import parse_website

from src.database.db_init import DEFAULT_SQLITE_DB_PATH

logger = logging.getLogger(__name__)


class DynamicParser:
    """动态网页内容解析器类"""

    def __init__(self, db_path=None):
        """
        初始化动态解析器

        Args:
            db_path: 可选的SQLite数据库路径
        """
        self.db_path = db_path if db_path else DEFAULT_SQLITE_DB_PATH
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def get_source_parser_code(self, source_id: int) -> Optional[str]:
        """
        从数据库获取资讯源的解析代码

        Args:
            source_id: 资讯源ID

        Returns:
            解析代码，如果没有则返回None
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询资讯源
            cursor.execute(
                "SELECT parser_code FROM news_sources WHERE id = ?", (source_id,)
            )
            result = cursor.fetchone()

            conn.close()

            if result and result[0]:
                return result[0]
            else:
                logger.warning(f"资讯源 {source_id} 没有解析代码")
                return None
        except Exception as e:
            logger.error(f"获取资讯源解析代码失败: {str(e)}", exc_info=True)
            return None

    def load_parser_module(self, parser_code: str) -> Optional[Any]:
        """
        加载解析模块

        Args:
            parser_code: 解析代码

        Returns:
            解析模块，如果加载失败则返回None
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
                f.write(parser_code.encode("utf-8"))
                temp_file = f.name

            try:
                # 动态导入
                spec = importlib.util.spec_from_file_location(
                    "dynamic_parser_module", temp_file
                )
                parser_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(parser_module)

                return parser_module
            finally:
                # 删除临时文件
                try:
                    os.unlink(temp_file)
                except:
                    pass
        except Exception as e:
            logger.error(f"加载解析模块失败: {str(e)}", exc_info=True)
            return None

    def fetch_website_content(self, url: str) -> Optional[str]:
        """
        获取网站内容

        Args:
            url: 网站URL

        Returns:
            网站内容，如果获取失败则返回None
        """
        try:
            # 发送请求
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            return response.text
        except Exception as e:
            logger.error(f"获取网站内容失败: {url}, {str(e)}", exc_info=True)
            return None

    def parse_source(self, source_id: int) -> List[Dict[str, Any]]:
        """
        解析资讯源内容

        Args:
            source_id: 资讯源ID

        Returns:
            解析结果列表
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询资讯源
            cursor.execute(
                "SELECT name, url, parser_code FROM news_sources WHERE id = ?",
                (source_id,),
            )
            result = cursor.fetchone()

            conn.close()

            if not result:
                logger.warning(f"未找到资讯源: {source_id}")
                return []

            name, url, parser_code = result

            if not parser_code:
                logger.warning(f"资讯源 {name} 没有解析代码")
                return []

            # 获取网站内容
            html_content = self.fetch_website_content(url)
            if not html_content:
                return []

            # 加载解析模块
            parser_module = self.load_parser_module(parser_code)
            if not parser_module:
                return []

            # 调用解析函数
            if hasattr(parser_module, "parse_website"):
                try:
                    results = parser_module.parse_website(html_content)
                    logger.info(f"资讯源 {name} 解析成功，获取到 {len(results)} 条资讯")
                    return results
                except Exception as e:
                    logger.error(f"执行解析函数失败: {str(e)}", exc_info=True)
                    return []
            else:
                logger.warning(f"解析模块没有parse_website函数")
                return []

            # results = parse_website(html_content)
            # return results

        except Exception as e:
            logger.error(f"解析资讯源失败: {str(e)}", exc_info=True)
            return []

    def parse_all_sources(self) -> Dict[int, List[Dict[str, Any]]]:
        """
        解析所有资讯源

        Returns:
            解析结果字典，键为资讯源ID，值为解析结果列表
        """
        results = {}

        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询所有资讯源
            cursor.execute("SELECT id FROM news_sources WHERE parser_code IS NOT NULL")
            sources = cursor.fetchall()

            conn.close()

            # 解析每个资讯源
            for (source_id,) in sources:
                source_results = self.parse_source(source_id)
                results[source_id] = source_results

            return results
        except Exception as e:
            logger.error(f"解析所有资讯源失败: {str(e)}", exc_info=True)
            return results


# 创建单例实例
dynamic_parser = DynamicParser()
