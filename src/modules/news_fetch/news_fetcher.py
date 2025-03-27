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

from .web_crawler import WebCrawler

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
        self.web_crawler = WebCrawler()
        self._load_sources()
    
    def _load_sources(self) -> None:
        """从数据库加载资讯源配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, name, url, type, category, active FROM news_sources WHERE active = 1")
            sources = cursor.fetchall()
            
            self.sources = [
                {
                    'id': src[0],
                    'name': src[1],
                    'url': src[2],
                    'type': src[3],
                    'category': src[4],
                    'active': bool(src[5])
                }
                for src in sources
            ]
            
            conn.close()
            logger.info(f"已加载 {len(self.sources)} 个活跃资讯源")
        except Exception as e:
            logger.error(f"加载资讯源失败: {str(e)}", exc_info=True)
            # 如果数据库为空或出错，尝试从sources.json加载
            try:
                import json
                import os
                
                # 获取sources.json文件路径
                current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                sources_file = os.path.join(current_dir, 'database', 'sources.json')
                
                # 加载资讯源
                with open(sources_file, 'r', encoding='utf-8') as f:
                    sources = json.load(f)
                
                self.sources = []
                for i, source in enumerate(sources, 1):
                    self.sources.append({
                        'id': i,
                        'name': source["name"],
                        'url': source["url"],
                        'type': source["type"],
                        'category': source["category"],
                        'active': bool(source["active"])
                    })
                
                logger.info(f"已从sources.json加载 {len(self.sources)} 个资讯源")
            except Exception as ex:
                logger.error(f"从sources.json加载资讯源失败: {str(ex)}", exc_info=True)
                # 如果从sources.json加载也失败，使用硬编码的默认资讯源
                self.sources = [
                    {
                        'id': 1,
                        'name': '机器之心',
                        'url': 'https://www.jiqizhixin.com/rss',
                        'type': 'RSS',
                        'category': '新闻',
                        'active': True
                    },
                    {
                        'id': 2,
                        'name': '雷锋网AI频道',
                        'url': 'https://www.leiphone.com/feed',
                        'type': 'RSS',
                        'category': '新闻',
                        'active': True
                    }
                ]
                logger.info("使用默认资讯源")
    
    def fetch_all(self, categories: Optional[List[str]] = None) -> int:
        """
        获取所有活跃资讯源的内容
        
        Args:
            categories: 可选的分类过滤，None表示获取全部分类
            
        Returns:
            获取的资讯数量
        """
        total_fetched = 0
        
        for source in self.sources:
            # 如果指定了分类过滤，且当前源不在过滤范围内，则跳过
            if categories and source['category'] not in categories:
                continue
                
            # 根据资讯源类型选择不同的获取方法
            if source['type'] == 'RSS':
                fetched = self._fetch_rss(source)
            elif source['type'] == 'Webpage':
                news_list = self.web_crawler.fetch_webpage(source)
                fetched = self._save_news_list(news_list)
                logger.info(f"从网页源 {source['name']} 更新了 {fetched} 条资讯")
            else:
                logger.warning(f"不支持的资讯源类型: {source['type']}")
                continue
                
            total_fetched += fetched
            # 添加短暂延迟，避免频繁请求被封
            time.sleep(1)
        
        return total_fetched    
    
    def _fetch_rss(self, source: Dict[str, Any]) -> int:
        """
        从RSS源获取资讯
        
        Args:
            source: 资讯源配置
            
        Returns:
            获取的资讯数量
        """
        try:
            logger.info(f"正在从RSS源 {source['name']} 获取资讯")
            
            # 请求头，某些资讯源需要合适的User-Agent
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive'
            }
            
            # 对于某些特殊的RSS源，使用requests先获取内容
            if source['name'] in ['arXiv CS.AI']:
                # arXiv有时需要直接请求，然后手动解析内容
                try:
                    response = requests.get(source['url'], headers=headers, timeout=30)
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                except Exception as e:
                    logger.error(f"arXiv CS.AI请求失败: {str(e)}")
                    return 0
            else:
                # 普通RSS源的处理
                feed = feedparser.parse(source['url'])

            # 检查feed状态和内容
            if hasattr(feed, 'status') and feed.status != 200:
                logger.warning(f"RSS源 {source['name']} 返回状态码 {feed.status}")
                return 0
            
            # 确保feed.entries存在且非空
            if not hasattr(feed, 'entries') or len(feed.entries) == 0:
                logger.warning(f"RSS源 {source['name']} 没有返回任何条目")
                return 0
            
            logger.info(f"RSS源 {source['name']} 请求成功，获取到 {len(feed.entries)} 条记录")

            # 获取内容
            count = 0
            for entry in feed.entries:
                # 提取标题和链接
                title = entry.title if hasattr(entry, 'title') else "无标题"
                url = entry.link if hasattr(entry, 'link') else None
                
                if not url:
                    continue
                
                # 尝试提取发布日期
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        publish_date = datetime(entry.published_parsed.tm_year,
                                                 entry.published_parsed.tm_mon,
                                                   entry.published_parsed.tm_mday).strftime('%Y-%m-%d')
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        publish_date = datetime(entry.updated_parsed.tm_year,
                                                 entry.updated_parsed.tm_mon,
                                                   entry.updated_parsed.tm_mday).strftime('%Y-%m-%d')
                    elif hasattr(entry, 'published') and entry.published:
                        publish_date = entry.published
                    else:
                        publish_date = datetime.now().strftime('%Y-%m-%d')
                except:
                    publish_date = datetime.now().strftime('%Y-%m-%d')
                
                # 尝试提取内容
                content = ""
                if hasattr(entry, 'summary') and entry.summary:
                    # 如果是arxiv，'summary' 中找'Abstract:'后面的内容
                    if source['name'] == 'arXiv CS.AI':
                        content = entry.summary.split('Abstract:')[1]
                    else:
                        content = entry.summary
                elif hasattr(entry, 'description') and entry.description:
                    content = entry.description
                elif hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].value
                else:
                    content = "无法获取内容，请访问原始链接查看。"
                
                # 清理HTML标签
                content = self.web_crawler.clean_html(content)
                
                # 保存到数据库
                if self._save_news(title, url, source['name'], source['category'], publish_date, content):
                    count += 1
            
            logger.info(f"从RSS源 {source['name']} 更新了 {count} 条资讯")
            return count
        except Exception as e:
            logger.error(f"从RSS源 {source['name']} 获取资讯失败: {str(e)}", exc_info=True)
            return 0
    
    def _save_news_list(self, news_list: List[Dict[str, Any]]) -> int:
        """
        保存资讯列表到数据库
        
        Args:
            news_list: 资讯列表
            
        Returns:
            成功保存的资讯数量
        """
        count = 0
        for news in news_list:
            if self._save_news(
                news['title'], 
                news['url'], 
                news['source'], 
                news['category'], 
                news['publish_date'], 
                news['content']
            ):
                count += 1
        return count

    def _save_news(self, title: str, url: str, source: str, category: str, 
                  publish_date: str, content: str) -> bool:
        """
        保存资讯到数据库
        
        Args:
            title: 资讯标题
            url: 资讯URL
            source: 资讯来源
            category: 资讯分类
            publish_date: 发布日期
            content: 资讯内容
            
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查是否已存在相同URL的资讯
            cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
            existing = cursor.fetchone()
            
            if existing:
                logger.debug(f"资讯已存在，跳过: {title}")
                conn.close()
                return False
            
            # 获取当前时间作为抓取时间
            fetch_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 插入新资讯
            cursor.execute(
                "INSERT INTO news (title, url, source, category, publish_date, fetch_date, content, analyzed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title, url, source, category, publish_date, fetch_date, content, 0)
            )
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"保存资讯失败: {str(e)}", exc_info=True)
            return False 