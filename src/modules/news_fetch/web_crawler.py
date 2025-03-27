#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
网页爬取模块
负责从各类网页源爬取内容
"""

import logging
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)

class WebCrawler:
    """网页爬取器类"""
    
    def __init__(self):
        """初始化网页爬取器"""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
        }
    
    def fetch_webpage(self, source: Dict[str, Any]) -> list:
        """
        从网页源获取资讯
        
        Args:
            source: 资讯源配置
            
        Returns:
            list: 资讯列表  
        """
        try:
            logger.info(f"正在从网页源 {source['name']} 获取资讯")
            
            # 根据不同的网站使用不同的解析策略
            if '36kr.com' in source['url']:
                response = requests.get(source['url'], headers=self.headers, timeout=30)
                response.raise_for_status()  # 如果请求失败则抛出异常
                return self.parse_36kr(response.text, source)
            elif 'paperswithcode.com' in source['url']:
                # # 动态解析
                # return self.parse_paperswithcode(source)
                # 静态解析
                return self.parse_paperswithcode_static(source)
            else:
                logger.warning(f"未实现对 {source['name']} 的解析策略")
                return []
                
        except Exception as e:
            logger.error(f"从网页源 {source['name']} 获取资讯失败: {str(e)}", exc_info=True)
            return []
    
    def parse_36kr(self, html_content: str, source: Dict[str, Any]) -> list:
        """
        解析36氪网页内容
        
        Args:
            html_content: 网页HTML内容
            source: 资讯源配置
            
        Returns:
            list: 资讯列表
        """
        try:
            news_list = []
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 36氪AI频道的文章列表
            article_elements = soup.find_all('div', class_='kr-flow-article-item')
            
            for article in article_elements:
                try:
                    # 提取标题和链接
                    title_element = article.find('a', class_='article-item-title')
                    if not title_element:
                        continue
                        
                    title = title_element.text.strip()
                    url = 'https://36kr.com' + title_element['href'] if title_element.has_attr('href') else None
                    
                    if not url:
                        continue
                    
                    # 提取发布日期
                    date_element = article.find('span', class_='kr-flow-bar-time')
                    publish_date = date_element.text.strip() if date_element else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 标准化日期格式
                    try:
                        # 处理"x分钟前"、"x小时前"等格式
                        if '分钟前' in publish_date:
                            minutes = int(publish_date.replace('分钟前', '').strip())
                            publish_date = (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
                        elif '小时前' in publish_date:
                            hours = int(publish_date.replace('小时前', '').strip())
                            publish_date = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
                        elif '天前' in publish_date:
                            days = int(publish_date.replace('天前', '').strip())
                            publish_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                        elif '昨天' in publish_date:
                            publish_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            # 尝试解析其他日期格式
                            publish_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        publish_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 提取描述
                    description_element = article.find('a', class_='article-item-description')
                    content = description_element.text.strip() if description_element else "无法获取内容，请访问原始链接查看。"
                    
                    # 获取文章详情（可选）
                    if url:
                        try:
                            # 发送请求获取文章详情页
                            article_response = requests.get(url, headers=self.headers, timeout=10)
                            
                            if article_response.status_code == 200:
                                article_soup = BeautifulSoup(article_response.text, 'html.parser')
                                article_content = article_soup.select_one('div.article-content')
                                if article_content:
                                    content = article_content.text.strip()
                        except Exception as e:
                            logger.warning(f"获取文章详情失败: {url}, {str(e)}")
                    
                    # 添加到新闻列表
                    news_list.append({
                        'title': title,
                        'url': url,
                        'source': source['name'],
                        'category': source['category'],
                        'publish_date': publish_date,
                        'content': content
                    })
                        
                except Exception as e:
                    logger.warning(f"解析文章失败: {str(e)}")
                    continue
            
            count = len(news_list)
            logger.info(f"从网页源 {source['name']} 获取了 {count} 条资讯")
            return news_list
        except Exception as e:
            logger.error(f"解析36氪内容失败: {str(e)}", exc_info=True)
            return []
    
    # 动态获取paperswithcode的论文列表
    def parse_paperswithcode(self, source: Dict[str, Any]) -> list:
        """
        解析PapersWithCode网页内容
        
        Args:
            json_content: 网页JSON内容
            source: 资讯源配置
            
        Returns:
            list: 资讯列表
        """
        # 配置 ChromeDriver 路径
        chrome_driver_path = r"C:\tools\chromedriver-win32\chromedriver.exe"  # 替换为实际的 chromedriver 路径
        service = Service(chrome_driver_path)
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")  # 无界面模式
        options.add_argument("--no-sandbox") # 禁用沙盒
        options.add_argument("--disable-dev-shm-usage") # 禁用共享内存
        options.add_argument("--disable-gpu") # 禁用GPU
        options.add_argument("--start-maximized") # 最大化窗口
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36")
    
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(source['url'])

        time.sleep(5)  # 等待页面加载

        # 抓取论文列表
        paper_elements = driver.find_elements(By.CLASS_NAME, "paper-card")
            
        try:
            papers = []
            for paper in paper_elements:
                try:
                    # 获取论文标题
                    title_element = paper.find_element(By.TAG_NAME, "h1")
                    title = title_element.text.strip()

                    # 获取论文链接
                    link_element = paper.find_element(By.TAG_NAME, "a") 
                    url = link_element.get_attribute("href")

                    # 获取论文简介
                    description_element = paper.find_element(By.CLASS_NAME, "item-strip-abstract")
                    content = description_element.text.strip()

                    # 获取代码链接
                    code_element = paper.find_element(By.CLASS_NAME, "item-github-link")
                    code_link = code_element.find_element(By.TAG_NAME, "a").get_attribute("href")

                    # 获取发表时间
                    time_element = paper.find_element(By.CLASS_NAME, "item-date-pub")
                    publish_date = time_element.text.strip()

                    papers.append({
                        'title': title,
                        'url': url,
                        'source': source['name'],
                        'category': source['category'], 
                        'publish_date': publish_date,
                        'content': content,
                        'code_link': code_link
                    })
                except Exception as e:
                    logger.error(f"提取论文数据失败: {str(e)}")
                    continue

            count = len(papers)
            logger.info(f"从网页源 {source['name']} 获取了 {count} 条资讯")
            return papers

        except Exception as e:
            logger.error(f"解析PapersWithCode内容失败: {str(e)}", exc_info=True)
            return []
        
    # 静态获取paperswithcode的论文列表
    def parse_paperswithcode_static(self, source: Dict[str, Any]) -> list:
        """
        解析PapersWithCode网页内容
        """
        try:
            response = requests.get(source['url'], headers=self.headers, timeout=30)
            response.raise_for_status()  # 如果请求失败则抛出异常
            
            soup = BeautifulSoup(response.text, 'html.parser')
            paper_elements = soup.find_all('div', class_='paper-card')
            papers = []
            for paper in paper_elements:
                # 提取标题与链接
                title_tag = paper.find('h1').find('a')
                if title_tag:
                    title = title_tag.text.strip()
                    url = title_tag['href']
                else:
                    title = ""
                    url = ""
                    
                # 提取发布日期
                date_tag = paper.find('span', class_='author-name-text item-date-pub')
                if date_tag:
                    publish_date = date_tag.text.strip()
                else:
                    publish_date = ""
                    
                # 提取内容
                content_tag = paper.find('p', class_='item-strip-abstract')
                if content_tag:
                    content = content_tag.text.strip()
                else:
                    content = ""
                    
                # 提取代码链接
                code_link_tag = paper.find('span', class_='item-github-link')
                if code_link_tag:
                    code_link = code_link_tag.find('a')['href'] if code_link_tag and code_link_tag.find('a') else ""
                else:
                    code_link = ""
                
                papers.append({
                    'title': title,
                    'url': url,
                    'source': source['name'],
                    'category': source['category'],
                    'publish_date': publish_date,
                    'content': content,
                    'code_link': code_link
                })
            return papers
        except Exception as e:
            logger.error(f"从网页源 {source['name']} 获取资讯失败: {str(e)}", exc_info=True)
            return []
    
    def clean_html(self, html_content: str) -> str:
        """
        清理HTML内容，提取纯文本
        
        Args:
            html_content: HTML内容
            
        Returns:
            清理后的纯文本
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator='\n', strip=True)
        except Exception as e:
            logger.error(f"清理HTML内容失败: {str(e)}", exc_info=True)
            return html_content 