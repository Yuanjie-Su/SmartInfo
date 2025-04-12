# src/core/crawler.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
from typing import List, Dict, Optional, Tuple, AsyncGenerator, Any
from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    Playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)
from bs4 import BeautifulSoup, Tag, NavigableString
import aiohttp
import charset_normalizer
from urllib.parse import urljoin
import time
import os

# 导入html_process模块的函数
from backend.utils.html_process import clean_html, format_html, clean_and_format_html, DEFAULT_EXCLUDE_TAGS, DEFAULT_EXCLUDE_SELECTORS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Aiohttp Crawler Class ---
class AiohttpCrawler:
    """
    An async crawler using aiohttp for fetching web content.
    Uses html_process module to clean and format content.
    """
    
    def __init__(
        self,
        max_concurrent_requests: int = 10, 
        request_timeout: int = 30,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        self.max_concurrent_requests = max_concurrent_requests
        self.request_timeout = request_timeout
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.user_agent = user_agent or "SmartInfo/1.0"
        self.headers = headers or {}
        if not 'User-Agent' in self.headers and self.user_agent:
            self.headers['User-Agent'] = self.user_agent
            
    async def _fetch_single(
        self,
        session: aiohttp.ClientSession,
        url: str,
        output_format: str = 'markdown',
        exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
        exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
        markdownify_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """获取单个URL的内容并进行处理"""
        html_content = ""
        error_message = ""
        final_url = url
        formatted_content = ""
        fetch_start_time = time.time()
        
        async with self.semaphore:
            try:
                logger.info(f"[Worker] 正在抓取: {url}")
                async with session.get(
                    url, 
                    timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                    allow_redirects=True
                ) as response:
                    response.raise_for_status()
                    final_url = str(response.url)
                    
                    raw_content = await response.read()
                    
                    # 尝试解码内容
                    encoding = response.charset
                    try:
                        if encoding:
                            logger.debug(f"使用响应头中的编码: {encoding}")
                            html_content = raw_content.decode(encoding, errors='replace')
                        else:
                            # 如果没有指定编码，使用charset-normalizer检测
                            matches = charset_normalizer.from_bytes(raw_content).best()
                            if matches:
                                detected_encoding = matches.encoding
                                logger.debug(f"检测到的编码: {detected_encoding}")
                                html_content = raw_content.decode(detected_encoding, errors='replace')
                            else:
                                logger.warning(f"无法检测到编码，使用utf-8")
                                html_content = raw_content.decode('utf-8', errors='replace')
                    except Exception as decode_err:
                        error_message = f"解码错误: {decode_err}"
                        logger.error(f"解码{url}时出错: {decode_err}")
                        return {
                            "original_url": url,
                            "final_url": final_url,
                            "content": "",
                            "error": error_message
                        }
                
                # 使用html_process模块处理HTML内容
                logger.debug(f"正在清理和格式化HTML: {final_url}")
                formatted_content = clean_and_format_html(html_content, final_url, output_format, exclude_tags, exclude_selectors, markdownify_options)
                
                fetch_duration = time.time() - fetch_start_time
                logger.info(f"[Worker] 成功处理: {final_url} 用时{fetch_duration:.2f}秒")
                
            except aiohttp.ClientResponseError as e:
                error_message = f"HTTP错误: {e.status} {e.message}"
                logger.error(f"{url}的HTTP错误: {e.status} - {e.message}")
            except asyncio.TimeoutError:
                error_message = f"请求超时 (>{self.request_timeout}秒)"
                logger.error(f"{url}请求超时")
            except aiohttp.ClientError as e:
                error_message = f"客户端错误: {e}"
                logger.error(f"{url}的客户端错误: {e}")
            except Exception as e:
                error_message = f"意外错误: {e}"
                logger.exception(f"抓取{url}时出现意外错误")
                
        return {
            "original_url": url,
            "final_url": final_url,
            "content": formatted_content,
            "error": error_message
        }
        
    async def process_urls(
        self,
        urls: List[str],
        output_format: str = 'markdown',
        exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
        exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
        markdownify_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """处理URL列表并生成结果，与Playwright版本兼容的接口"""
        if not urls:
            return  # 空URL列表，直接返回
            
        # 创建会话
        session_timeout = aiohttp.ClientTimeout(total=None)  # 整体会话无超时，单个请求有超时
        async with aiohttp.ClientSession(headers=self.headers, timeout=session_timeout) as session:
            tasks = [
                asyncio.create_task(
                    self._fetch_single(
                        session, url, output_format, exclude_tags, exclude_selectors, markdownify_options=markdownify_options
                    ),
                    name=f"fetch_{url[:50]}"  # 为调试添加任务名称
                )
                for url in urls
            ]
            
            # 使用as_completed迭代完成的任务并yield结果
            for future in asyncio.as_completed(tasks):
                try:
                    result = await future
                    yield result
                    if isinstance(result, dict) and result.get("error"):
                        logger.warning(f"URL {result.get('original_url', 'unknown')} 处理出错: {result['error']}")
                except Exception as e:
                    # 处理任务执行时的异常
                    task_name = future.get_name() if hasattr(future, 'get_name') else "unknown_task"
                    logger.error(f"任务 {task_name} 抛出异常: {e}", exc_info=True)
                    # 从任务名称提取URL
                    original_url = task_name.replace("fetch_", "") if task_name.startswith("fetch_") else "unknown_url"
                    yield {
                        "original_url": original_url,
                        "final_url": original_url,
                        "content": "",
                        "error": f"任务执行失败: {e}"
                    }

# --- Playwright Crawler Class ---

class PlaywrightCrawler:
    """
    An async crawler using Playwright for fetching and cleaning web content.
    Yields results asynchronously. Manages its browser instance lifecycle.
    """

    # --- Initialize ---
    def __init__(
        self,
        headless: bool = True,
        max_concurrent_pages: int = 5,
        page_timeout: int = 60000, # ms
        browser_args: Optional[Dict[str, Any]] = None,
        user_agent: Optional[str] = None,
    ):
        self.headless = headless
        self.page_timeout = page_timeout
        self.browser_args = browser_args or {}
        self.user_agent = user_agent
        self.semaphore = asyncio.Semaphore(max_concurrent_pages)
        self.pw_instance: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._start_lock = asyncio.Lock()

    async def _ensure_browser_started(self):
        """Starts Playwright and browser if not already running, using a lock."""
        async with self._start_lock:
            if self.browser and self.browser.is_connected(): return
            if self.pw_instance is None:
                 try:
                     logger.info("Starting Playwright..."); self.pw_instance = await async_playwright().start()
                 except Exception as e: raise RuntimeError("Could not start Playwright") from e
            try:
                logger.info(f"Launching browser (headless={self.headless})...");
                self.browser = await self.pw_instance.chromium.launch(headless=self.headless, args=self.browser_args.get("args"))
                logger.info("Browser launched successfully.")
            except Exception as e: await self.shutdown(); raise RuntimeError("Could not launch browser") from e

    async def shutdown(self):
        """Shuts down the browser and Playwright instance."""
        logger.info("Shutting down crawler...")
        async with self._start_lock:
            if self.browser:
                try: await self.browser.close(); logger.info("Browser closed.")
                except Exception as e: logger.error(f"Error closing browser: {e}")
                finally: self.browser = None
            if self.pw_instance:
                try: await self.pw_instance.stop(); logger.info("Playwright stopped.")
                except Exception as e: logger.error(f"Error stopping Playwright: {e}")
                finally: self.pw_instance = None
        logger.info("Crawler shutdown complete.")

    async def _fetch_single(
        self,
        url: str,
        output_format: str,
        exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
        exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
        scroll_page: bool = True,
        max_retries: int = 2,
        markdownify_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Fetches and processes a single URL, handling semaphore and retries."""
        await self._ensure_browser_started()
        if not self.browser: return {"original_url": url, "content": "", "error": "Browser initialization failed"}
        page: Optional[Page] = None; context: Optional[Any] = None
        formatted_output = ""; error_message = ""; final_url = url
        fetch_start_time = time.time()
        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    # logger.info(f"[Worker Attempt {attempt+1}/{max_retries}] Processing URL: {url}") # Less verbose
                    context = await self.browser.new_context(user_agent=self.user_agent)
                    page = await context.new_page()
                    page.set_default_timeout(self.page_timeout)
                    await page.goto(url, wait_until='domcontentloaded')
                    final_url = page.url
                    if scroll_page: await self._scroll_page(page)
                    try: await page.wait_for_load_state('networkidle', timeout=15000); # logger.debug(f"Network is idle for {final_url}")
                    except PlaywrightTimeoutError: logger.warning(f"Network idle wait timed out for {final_url}. Proceeding.")
                    except PlaywrightError as e: logger.warning(f"Network idle wait failed for {final_url}: {e}. Proceeding.")
                    # logger.debug(f"Fetching final HTML content for: {final_url}")
                    html_content = await page.content()
                    
                    # 使用html_process模块处理HTML
                    formatted_output = clean_and_format_html(html_content, final_url, output_format, exclude_tags, exclude_selectors, markdownify_options)
                    
                    fetch_duration = time.time() - fetch_start_time
                    logger.info(f"[Worker] Successfully processed: {final_url} in {fetch_duration:.2f}s")
                    error_message = ""
                    break # Success
                except PlaywrightTimeoutError as e: error_message = f"TimeoutError ({e.__class__.__name__}) for {url}: {str(e).splitlines()[0]}"
                except PlaywrightError as e: error_message = f"PlaywrightError ({e.__class__.__name__}) for {url}: {str(e).splitlines()[0]}"
                except Exception as e: error_message = f"Unexpected error for {url}: {e}"
                finally:
                    if page: await page.close()
                    if context: await context.close()
                logger.error(f"{error_message} (Attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1: await asyncio.sleep(2 ** attempt)
            if error_message:
                 fetch_duration = time.time() - fetch_start_time
                 logger.error(f"Failed to process {url} after {max_retries} attempts in {fetch_duration:.2f}s. Last error: {error_message}")
        return {"original_url": url, "content": formatted_output, "error": error_message}

    async def _scroll_page(self, page: Page, scroll_delay: float = 0.6, max_scrolls: int = 10):
        """Internal scroll helper. Improved stability check."""
        # logger.debug(f"Scrolling page: {page.url}") # Less verbose
        try:
            last_height = await page.evaluate("document.body.scrollHeight"); scroll_count = 0; same_height_count = 0; MAX_SAME_HEIGHT = 3
            while scroll_count < max_scrolls:
                scroll_start_time = time.time()
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); await asyncio.sleep(scroll_delay)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    same_height_count += 1
                    if same_height_count >= MAX_SAME_HEIGHT: logger.debug(f"Scrolling stopped for {page.url} (height stable at {new_height})."); break
                else: same_height_count = 0
                last_height = new_height; scroll_count += 1; scroll_duration = time.time() - scroll_start_time
                # logger.debug(f"Scroll {scroll_count}/{max_scrolls} for {page.url}, height {new_height}, took {scroll_duration:.2f}s") # Less verbose
                await asyncio.sleep(0.1)
            # logger.info(f"Finished scrolling for {page.url} after {scroll_count} scrolls.") # Less verbose
        except PlaywrightError as e: logger.warning(f"Scrolling failed for {page.url}: {e}")
        except Exception as e: logger.warning(f"Unexpected error during scrolling for {page.url}: {e}", exc_info=True)

    # --- Modified process_urls ---
    async def process_urls(
        self,
        urls: List[str],
        output_format: str = 'markdown',
        exclude_tags: Optional[List[str]] = DEFAULT_EXCLUDE_TAGS,
        exclude_selectors: Optional[List[str]] = DEFAULT_EXCLUDE_SELECTORS,
        scroll_pages: bool = True,
        markdownify_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Processes a list of URLs concurrently and yields results as they become available."""
        if not self.browser or not self.browser.is_connected():
            await self._ensure_browser_started()

        if not urls:
            return

        tasks = [
            asyncio.create_task(
                self._fetch_single(url, output_format, exclude_tags, exclude_selectors, scroll_pages, markdownify_options=markdownify_options),
                name=f"fetch_{url[:50]}"
            )
            for url in urls
        ]

        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                yield result
                if isinstance(result, dict) and result.get("error"):
                     logger.warning(f"URL {result.get('original_url', 'unknown')} processed with error: {result['error']}")
            except Exception as e:
                task_name = future.get_name() if hasattr(future, 'get_name') else "unknown_task"
                logger.error(f"Task {task_name} raised an unexpected exception: {e}", exc_info=True)
                original_url = task_name.replace("fetch_", "") if task_name.startswith("fetch_") else "unknown_url"
                yield {
                    "original_url": original_url,
                    "final_url": original_url,
                    "content": "",
                    "error": f"Task execution failed: {e}"
                }

# --- Example Usage (Modified to use async for loop) ---
async def main_playwright():
    urls_to_fetch = [
        "https://hub.baai.ac.cn/",
        "https://www.jiqizhixin.com",
        "https://www.xinhuanet.com",
        "https://pro.jiqizhixin.com/reference/ff25ec2f-ffcf-4d75-9503-46ab55afc999",
    ]
    desired_format = "markdown"
    crawler = PlaywrightCrawler(headless=True, max_concurrent_pages=4, page_timeout=20000)

    output_dir = "crawl_output_playwright"
    os.makedirs(output_dir, exist_ok=True)
    results_count = 0
    errors_count = 0

    try:
        start_time = time.time()
        async for result in crawler.process_urls(
            urls=urls_to_fetch,
            output_format=desired_format,
            scroll_pages=True,
            markdownify_options={
                'heading_style': 'ATX',
                'strip': ['img', 'picture', 'svg', 'figure', 'figcaption'],
            },
        ):
            results_count += 1
            print("-" * 40)
            print(f"Received result #{results_count}")
            print(f"Original URL: {result['original_url']}")
            if result["error"]:
                errors_count += 1
                print(f"Error: {result['error']}")
            else:
                filename_part = result['original_url'].split('//')[-1].replace('/', '_').replace('?', '_').replace(':', '_')
                filename = os.path.join(output_dir, f"{filename_part}.md")
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"# Original URL: {result['original_url']}\n")
                        f.write(result["content"])
                    print(f"Output saved to: {filename}")
                except Exception as write_err:
                    print(f"Error writing output file {filename}: {write_err}")
                print(f"Content Length: {len(result['content'])}")
            print("-" * 40)

        end_time = time.time()
        logger.info(f"Processing completed in {end_time - start_time:.2f} seconds.")
        logger.info(f"Total results received: {results_count}, Errors: {errors_count}")

    except Exception as main_err:
        logger.exception("An error occurred in the main execution block.")
    finally:
        await crawler.shutdown()

# --- Example Usage for AiohttpCrawler ---
async def main_aiohttp():
    urls_to_fetch = [
        "https://hub.baai.ac.cn/view/44762",
        "https://pro.jiqizhixin.com/reference/ff25ec2f-ffcf-4d75-9503-46ab55afc999",
        "http://www.news.cn/politics/20250409/c3d08c8507bc412ba22f174ac063bea9/c.html",
    ]
    desired_format = "markdown"
    crawler = AiohttpCrawler(max_concurrent_requests=5, request_timeout=30)

    output_dir = "crawl_output_aiohttp"
    os.makedirs(output_dir, exist_ok=True)
    results_count = 0
    errors_count = 0

    try:
        start_time = time.time()
        async for result in crawler.process_urls(
            urls=urls_to_fetch,
            output_format=desired_format,
            markdownify_options={
                'heading_style': 'ATX',
                'strip': ['img', 'picture', 'svg', 'figure', 'figcaption'],
            },
        ):
            results_count += 1
            print("-" * 40)
            print(f"Received result #{results_count}")
            print(f"Original URL: {result['original_url']}")
            if result["error"]:
                errors_count += 1
                print(f"Error: {result['error']}")
            else:
                filename_part = result['original_url'].split('//')[-1].replace('/', '_').replace('?', '_').replace(':', '_')
                filename = os.path.join(output_dir, f"{filename_part}.md")
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"# Original URL: {result['original_url']}\n")
                        f.write(result["content"])
                    print(f"Output saved to: {filename}")
                except Exception as write_err:
                    print(f"Error writing output file {filename}: {write_err}")
                print(f"Content Length: {len(result['content'])}")
            print("-" * 40)

        end_time = time.time()
        logger.info(f"Processing completed in {end_time - start_time:.2f} seconds.")
        logger.info(f"Total results received: {results_count}, Errors: {errors_count}")

    except Exception as main_err:
        logger.exception("An error occurred in the main execution block.")

if __name__ == "__main__":
    asyncio.run(main_playwright())
    # asyncio.run(main_aiohttp())