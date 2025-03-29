#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
URL分析器模块
负责分析URL网页内容并生成解析代码
"""

import logging
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, Any, Tuple, Optional
import sqlite3
from datetime import datetime

# 导入API客户端
from src.utils.api_client import api_client
from src.database.db_init import DEFAULT_SQLITE_DB_PATH

logger = logging.getLogger(__name__)


class URLAnalyzer:
    """URL分析器类，用于分析网页内容并生成解析代码"""

    def __init__(self):
        """
        初始化URL分析器
        """

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36"
        }

    def fetch_url_content(self, url: str) -> Tuple[bool, str]:
        """
        获取URL内容

        Args:
            url: 目标URL

        Returns:
            元组，包含是否成功和内容
        """
        try:
            # 发送请求获取页面内容
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            # 返回页面内容
            return True, response.text
        except Exception as e:
            logger.error(f"获取URL内容失败: {url}, {str(e)}", exc_info=True)
            return False, f"获取URL内容失败: {str(e)}"

    def preprocess_content(self, html_content: str) -> str:
        """
        预处理HTML内容，去除无关元素

        Args:
            html_content: HTML内容

        Returns:
            清理后的HTML内容
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # 返回清理后的完整页面
            return str(soup)
        except Exception as e:
            logger.error(f"预处理HTML内容失败: {str(e)}", exc_info=True)
            return html_content

    def generate_parser_code(self, url: str, html_content: str) -> Tuple[bool, str]:
        """
        生成解析代码

        Args:
            url: 目标URL
            html_content: 预处理后的HTML内容

        Returns:
            元组，包含是否成功和生成的代码
        """
        try:
            # 准备提示内容
            prompt = f"""
我需要你为以下URL和HTML内容生成一段Python代码，用于解析该网页内容并提取相关资讯信息。

URL: {url}

以下是该网页的部分HTML内容示例:
```html
{html_content}
```

请生成一个名为parse_website的Python函数，该函数接收HTML内容作为输入，返回一个包含解析结果的列表。每个结果应该是一个包含以下字段的字典：
- title: 文章标题
- url: 文章链接 (若为相对链接需转换为绝对链接)
- publish_date: 发布日期 (不需要格式转换)
- content: 文章内容或摘要 (尽量提取最有信息量的部分)

函数应该使用BeautifulSoup库来解析HTML。确保代码能够健壮地处理各种边缘情况，避免因解析错误导致程序崩溃。

只需提供parse_website函数的代码，不要包含导入语句或其他说明，不要包含任何注释。代码应该简洁、高效并且有适当的错误处理。

注意：html_content不一定包含title、url、publish_date、content关键字，需要通过上下文识别。
"""

            # 调用API生成代码
            response = api_client.call_deepseek(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的Python爬虫工程师，擅长编写网页解析代码。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
                temperature=0,
            )

            if response["success"]:
                # 处理生成的代码
                generated_code = response["text"]

                # 提取代码块
                code_match = re.search(
                    r"```python\s*(.*?)\s*```", generated_code, re.DOTALL
                )
                if code_match:
                    code = code_match.group(1)
                else:
                    code = generated_code

                # 清理代码
                code = code.replace("```python", "").replace("```", "")
                code = code.strip()

                # 修复潜在的语法错误：处理转义字符和行延续字符
                code = code.encode("utf-8").decode("unicode_escape")

                # 移除所有行延续符并替换为单一空格（避免破坏代码逻辑）
                code = re.sub(r"\\\s*", " ", code)

                # 将 `\\n` 转换为真正的换行符
                code = code.replace("\\n", "\n")

                # 添加必要的换行符来确保代码格式正确
                code = re.sub(r";(\s*)", ";\n", code)

                # 确保代码以正确的形式结束 (避免 `SyntaxError`)
                if not code.endswith("\n"):
                    code += "\n"

                # 尝试编译代码来验证语法
                try:
                    compile(code, "<string>", "exec")
                except SyntaxError as e:
                    logger.warning(f"生成的代码包含语法错误，尝试修复: {str(e)}")
                    # 如果代码有语法错误，尝试使用更保守的方法生成基本代码模板
                    code = """
def parse_website(html_content):
    \"\"\"解析网页内容并提取资讯信息\"\"\"
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        results = []
        base_url = "{}"
        
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
                    item = {{}}
                    
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
                item = {{}}
                
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
""".format(
                        url
                    )

                # 添加必要的导入语句
                final_code = (
                    """
import logging
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

"""
                    + code
                )

                return True, final_code
            else:
                return False, f"生成解析代码失败: {response.get('error', '未知错误')}"
        except Exception as e:
            logger.error(f"生成解析代码失败: {str(e)}", exc_info=True)
            return False, f"生成解析代码失败: {str(e)}"

    def analyze_url(self, url: str) -> Dict[str, Any]:
        """
        分析URL并生成解析代码

        Args:
            url: 目标URL

        Returns:
            字典，包含是否成功和解析代码
        """
        result = {"success": False, "parser_code": ""}

        # 获取URL内容
        success, content = self.fetch_url_content(url)
        if not success:
            return result

        # 预处理内容
        processed_content = self.preprocess_content(content)

        # 生成解析代码
        success, code = self.generate_parser_code(url, processed_content)
        if not success:
            return result

        result["success"] = True
        result["parser_code"] = code

        return result


# 创建单例实例
url_analyzer = URLAnalyzer()
