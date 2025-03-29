
import logging
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def parse_website(html_content):
    """解析网页内容并提取资讯信息"""
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        results = []
        base_url = "https://www.jiqizhixin.com/"
        
        # 解析HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 查找所有可能的文章元素
        articles = soup.find_all(['article', 'div', 'li'], class_=lambda c: c and any(x in c for x in ['item', 'post', 'article', 'entry']))
        
        # 如果找不到明确的文章元素，尝试寻找链接和标题
        if not articles:
            # 寻找标题元素
            titles = soup.find_all(['h1', 'h2', 'h3'], class_=lambda c: c and any(x in c for x in ['title', 'headline', 'heading']))
            
            for title in titles:
                try:
                    item = {}
                    
                    # 提取标题
                    item['title'] = title.get_text(strip=True)
                    
                    # 查找链接（在标题中或其父元素中）
                    link = title.find('a') or title.parent.find('a')
                    if link and link.has_attr('href'):
                        item['url'] = urljoin(base_url, link['href'])
                    
                    # 查找日期
                    date_elem = title.find_next(['time', 'span', 'div'], class_=lambda c: c and any(x in c for x in ['date', 'time', 'meta', 'pub']))
                    if date_elem:
                        item['publish_date'] = date_elem.get_text(strip=True)
                    
                    # 查找内容
                    content_elem = title.find_next(['p', 'div'], class_=lambda c: c and any(x in c for x in ['content', 'summary', 'desc', 'excerpt']))
                    if content_elem:
                        item['content'] = content_elem.get_text(strip=True)
                    
                    # 只有当至少有标题和URL时才添加
                    if item.get('title') and item.get('url'):
                        results.append(item)
                except Exception:
                    continue
        
        # 处理找到的文章元素
        for article in articles:
            try:
                item = {}
                
                # 提取标题
                title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'], class_=lambda c: c and 'title' in str(c).lower() if c else False)
                if not title_elem:
                    title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                
                if title_elem:
                    item['title'] = title_elem.get_text(strip=True)
                    
                    # 查找链接
                    if title_elem.name == 'a' and title_elem.has_attr('href'):
                        item['url'] = urljoin(base_url, title_elem['href'])
                    else:
                        link = title_elem.find('a')
                        if link and link.has_attr('href'):
                            item['url'] = urljoin(base_url, link['href'])
                        else:
                            link = article.find('a')
                            if link and link.has_attr('href'):
                                item['url'] = urljoin(base_url, link['href'])
                
                # 查找日期
                date_elem = article.find(['time', 'span', 'div'], class_=lambda c: c and any(x in c for x in ['date', 'time', 'meta', 'pub']))
                if date_elem:
                    item['publish_date'] = date_elem.get_text(strip=True)
                
                # 提取内容/摘要
                content_elem = article.find(['p', 'div'], class_=lambda c: c and any(x in c for x in ['content', 'summary', 'desc', 'excerpt']))
                if content_elem:
                    item['content'] = content_elem.get_text(strip=True)
                    
                # 只有当至少有标题和URL时才添加
                if item.get('title') and item.get('url'):
                    results.append(item)
            except Exception:
                continue
        
        return results
    except Exception:
        return []
