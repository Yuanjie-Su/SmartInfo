# src/core/crawler.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time
import os
from typing import List, Dict, Optional, AsyncGenerator, Any, Set, Union, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Third-party imports
from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    Playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)
import aiohttp
import charset_normalizer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants for performance tuning
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 1.0  # Base delay in seconds
DEFAULT_JITTER_FACTOR = 0.1
DEFAULT_MAX_CONCURRENT_REQUESTS = 10

# ---- Retry Utilities ----
def calculate_backoff(attempt: int, base_delay: float = DEFAULT_RETRY_BASE_DELAY) -> float:
    """Calculate exponential backoff with jitter"""
    delay = base_delay * (2 ** attempt)
    jitter = delay * DEFAULT_JITTER_FACTOR
    return delay + random.uniform(-jitter, jitter)


# --- Aiohttp Crawler Class ---
class AiohttpCrawler:
    """
    A crawler that uses aiohttp to asynchronously fetch web content.
    """

    def __init__(
        self,
        max_concurrent_requests: int = 10,
        request_timeout: int = 30,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
    ):
        self.max_concurrent_requests = max_concurrent_requests
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.user_agent = user_agent or "SmartInfo/1.0"
        self.headers = headers or {}
        if "User-Agent" not in self.headers and self.user_agent:
            self.headers["User-Agent"] = self.user_agent
            
        # Add connection pooling settings
        self.conn_timeout = aiohttp.ClientTimeout(total=None)
        self.tcp_connector = None  # Will be initialized when session is created
        
        # Track processed domains to implement per-domain rate limiting
        self.domain_timestamps = {}
        self.domain_locks: Dict[str, asyncio.Lock] = {}

    async def _enforce_domain_rate_limit(self, url: str) -> None:
        """Enforce rate limiting per domain to avoid overloading servers"""
        domain = urlparse(url).netloc
        
        # Get or create a lock for this domain to enforce per-domain serialization
        lock = self.domain_locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self.domain_locks[domain] = lock

        async with lock:
            last_access = self.domain_timestamps.get(domain, 0)
            now = time.time()
            
            # If we've accessed this domain recently, wait a bit
            if now - last_access < 1.0:  # 1 second between requests to same domain
                delay = 1.0 - (now - last_access)
                await asyncio.sleep(delay)
                
            # Update the last access time
            self.domain_timestamps[domain] = time.time()

    async def _fetch_single(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> Dict[str, str]:
        """Fetch the raw HTML content of a single URL with retries."""
        # Enforce rate limiting
        await self._enforce_domain_rate_limit(url)
        
        html_content = ""
        error_message = ""
        final_url = url
        fetch_start_time = time.time()
        
        # Use semaphore to limit concurrent requests
        async with self.semaphore:
            retry_attempt = 0
            while retry_attempt <= self.max_retries:
                try:
                    logger.info(f"[Worker] Fetching: {url} (Attempt {retry_attempt+1})")
                    
                    # Improved request with proper timeout handling
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                        allow_redirects=True,
                        ssl=False,  # Skip SSL verification for better performance
                    ) as response:
                        response.raise_for_status()
                        final_url = str(response.url)

                        # Stream the content instead of loading it all at once
                        chunks = []
                        async for chunk in response.content.iter_chunked(8192):
                            chunks.append(chunk)
                            
                        raw_content = b''.join(chunks)

                        # Attempt to decode the content more efficiently
                        encoding = response.charset
                        try:
                            if encoding:
                                html_content = raw_content.decode(encoding, errors="replace")
                            else:
                                # Use faster charset detection
                                matches = charset_normalizer.from_bytes(raw_content).best()
                                if matches:
                                    detected_encoding = matches.encoding
                                    html_content = raw_content.decode(detected_encoding, errors="replace")
                                else:
                                    html_content = raw_content.decode("utf-8", errors="replace")
                                    
                        except Exception as decode_err:
                            error_message = f"Decoding error: {decode_err}"
                            logger.error(f"Error decoding {url}: {decode_err}")
                            return {
                                "original_url": url,
                                "final_url": final_url,
                                "content": "",
                                "error": error_message,
                            }

                    fetch_duration = time.time() - fetch_start_time
                    logger.info(
                        f"[Worker] Successfully fetched: {final_url} in {fetch_duration:.2f} seconds"
                    )
                    # Success - break out of retry loop
                    break
                    
                except aiohttp.ClientResponseError as e:
                    error_message = f"HTTP error: {e.status} {e.message}"
                    logger.error(f"HTTP error for {url}: {e.status} - {e.message}")
                except asyncio.TimeoutError:
                    error_message = f"Request timed out (>{self.request_timeout} seconds)"
                    logger.error(f"Request timed out for {url}")
                except aiohttp.ClientError as e:
                    error_message = f"Client error: {e}"
                    logger.error(f"Client error for {url}: {e}")
                except Exception as e:
                    error_message = f"Unexpected error: {e}"
                    logger.exception(f"Unexpected error while fetching {url}")
                    
                # Handle retries
                retry_attempt += 1
                if retry_attempt <= self.max_retries:
                    backoff = calculate_backoff(retry_attempt - 1)
                    logger.info(f"Retrying {url} in {backoff:.2f} seconds (attempt {retry_attempt}/{self.max_retries})")
                    await asyncio.sleep(backoff)
                    
        result = {
            "original_url": url,
            "final_url": final_url,
            "content": html_content,
            "error": error_message,
        }
            
        return result

    async def process_urls(
        self,
        urls: List[str],
        batch_size: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Process a list of URLs and yield results containing raw HTML.
        
        Args:
            urls: List of URLs to process
            batch_size: Optional batch size to process URLs in chunks
        """
        if not urls:
            return  # Empty URL list, return immediately
            
        # Determine batch size if not provided
        if batch_size is None:
            batch_size = min(len(urls), self.max_concurrent_requests * 2)
            
        # Create session with connection pooling
        self.tcp_connector = aiohttp.TCPConnector(
            limit=self.max_concurrent_requests,
            ttl_dns_cache=300,  # 5 minutes DNS cache TTL
            enable_cleanup_closed=True,
            force_close=False,  # Keep connections open for reuse
        )
        
        async with aiohttp.ClientSession(
            headers=self.headers,
            timeout=self.conn_timeout,
            connector=self.tcp_connector,
        ) as session:
            # Process URLs in batches for better resource management
            for i in range(0, len(urls), batch_size):
                batch = urls[i:i+batch_size]
                tasks = [
                    asyncio.create_task(
                        self._fetch_single(session, url),
                        name=f"fetch_{url[:50]}",
                    )
                    for url in batch
                ]
                
                # Process completed tasks
                for future in asyncio.as_completed(tasks):
                    try:
                        result = await future
                        yield result
                        if isinstance(result, dict) and result.get("error"):
                            logger.warning(
                                f"Error processing URL {result.get('original_url', 'unknown')}: {result['error']}"
                            )
                    except Exception as e:
                        task_name = future.get_name() if hasattr(future, "get_name") else "unknown_task"
                        logger.error(f"Task {task_name} raised an exception: {e}", exc_info=True)
                        
                        # Extract URL from task name
                        original_url = (
                            task_name.replace("fetch_", "")
                            if task_name.startswith("fetch_")
                            else "unknown_url"
                        )
                        yield {
                            "original_url": original_url,
                            "final_url": original_url,
                            "content": "",
                            "error": f"Task execution failed: {e}",
                        }
                        
                # Small pause between batches to avoid overwhelming resources
                if i + batch_size < len(urls):
                    await asyncio.sleep(0.5)

# ---- Playwright Crawler Class ----
class PlaywrightCrawler:
    """
    A crawler that uses Playwright to asynchronously fetch raw HTML content from web pages.
    Optimized for performance with browser context reuse and smart retries.
    
    Can be used as an async context manager:
    
    async with PlaywrightCrawler() as crawler:
        async for result in crawler.process_urls(urls):
            # Process result
    """

    def __init__(
            self,
            headless: bool = True,
            max_concurrent_pages: int = DEFAULT_MAX_CONCURRENT_REQUESTS,
            page_timeout: int = 10000,  # ms
            browser_args: Optional[Dict[str, Any]] = None,
            user_agent: Optional[str] = None,
            max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
        ):
            self.headless = headless
            self.page_timeout = page_timeout
            self.max_retries = max_retries
            self.browser_args = browser_args or {}
            self.user_agent = user_agent
            self.semaphore = asyncio.Semaphore(max_concurrent_pages)
            self.pw_instance: Optional[Playwright] = None
            self.browser: Optional[Browser] = None
            self._start_lock = asyncio.Lock()
            
            # Add performance optimizations
            self.context_pool = []
            self.context_pool_size = max_concurrent_pages
            self.context_pool_lock = asyncio.Lock()
            
            # Track processed domains to implement per-domain rate limiting
            self.domain_timestamps = {}
            self.domain_locks: Dict[str, asyncio.Lock] = {}

    async def __aenter__(self):
        """Async enter method for context manager support."""
        await self._ensure_browser_started()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager support."""
        await self.shutdown()
        return False  # Don't suppress exceptions

    async def _ensure_browser_started(self):
        """Use a lock to ensure Playwright and the browser are started (if not already running)."""
        async with self._start_lock:
            if self.browser and self.browser.is_connected():
                return
            if self.pw_instance is None:
                try:
                    logger.info("Starting Playwright...")
                    self.pw_instance = await async_playwright().start()
                except Exception as e:
                    raise RuntimeError("Unable to start Playwright") from e
            try:
                logger.info(f"Starting browser (headless={self.headless})...")
                launch_args = {
                    "headless": self.headless,
                }
                
                # Add chromium-specific args for better performance
                chromium_args = self.browser_args.get("args", [])
                if not any("disable-dev-shm-usage" in arg for arg in chromium_args):
                    chromium_args.append("--disable-dev-shm-usage")
                if not any("disable-gpu" in arg for arg in chromium_args):
                    chromium_args.append("--disable-gpu")
                if not any("disable-setuid-sandbox" in arg for arg in chromium_args):
                    chromium_args.append("--disable-setuid-sandbox")
                if not any("no-sandbox" in arg for arg in chromium_args):
                    chromium_args.append("--no-sandbox")
                
                # Add args to launch options if there are any
                if chromium_args:
                    launch_args["args"] = chromium_args
                
                self.browser = await self.pw_instance.chromium.launch(**launch_args)
                logger.info("Browser started successfully.")
                
                # Initialize context pool
                await self._initialize_context_pool()
            except Exception as e:
                await self.shutdown()
                raise RuntimeError(f"Unable to start browser: {e}") from e

    async def _initialize_context_pool(self):
        """Initialize a pool of browser contexts for performance"""
        async with self.context_pool_lock:
            logger.info(f"Initializing context pool with {self.context_pool_size} contexts")
            for _ in range(self.context_pool_size):
                context = await self.browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1280, "height": 720},
                    java_script_enabled=True,
                )
                self.context_pool.append({"context": context, "in_use": False})
            logger.info("Context pool initialized")

    async def _get_context_from_pool(self):
        """Get an available context from the pool or create a new one if needed"""
        async with self.context_pool_lock:
            # Try to find an available context
            for item in self.context_pool:
                if not item["in_use"]:
                    item["in_use"] = True
                    return item
            
            # If all contexts are in use, create a new one
            logger.info("All contexts in use, creating a new one")
            context = await self.browser.new_context(user_agent=self.user_agent)
            new_item = {"context": context, "in_use": True}
            self.context_pool.append(new_item)
            return new_item

    async def _return_context_to_pool(self, context_item):
        """Return a context to the pool"""
        async with self.context_pool_lock:
            for item in self.context_pool:
                if item["context"] == context_item["context"]:
                    item["in_use"] = False
                    break

    async def shutdown(self):
        """Close the browser and Playwright instance."""
        logger.info("Shutting down the crawler...")
        async with self._start_lock:
            # Close all contexts in the pool
            if hasattr(self, "context_pool") and self.context_pool:
                for item in self.context_pool:
                    try:
                        await item["context"].close()
                    except Exception as e:
                        logger.error(f"Error closing context: {e}")
                self.context_pool = []
                
            if self.browser:
                try:
                    await self.browser.close()
                    logger.info("Browser closed.")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
                finally:
                    self.browser = None
            if self.pw_instance:
                try:
                    await self.pw_instance.stop()
                    logger.info("Playwright stopped.")
                except Exception as e:
                    logger.error(f"Error stopping Playwright: {e}")
                finally:
                    self.pw_instance = None
        logger.info("Crawler shutdown complete.")

    async def _enforce_domain_rate_limit(self, url: str) -> None:
        """Enforce rate limiting per domain to avoid overloading servers"""
        domain = urlparse(url).netloc
        
        # Get or create a lock for this domain to enforce per-domain serialization
        lock = self.domain_locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self.domain_locks[domain] = lock

        async with lock:
            last_access = self.domain_timestamps.get(domain, 0)
            now = time.time()
            
            # If we've accessed this domain recently, wait a bit
            if now - last_access < 1.0:  # 1 second between requests to same domain
                delay = 1.0 - (now - last_access)
                await asyncio.sleep(delay)
                
            # Update the last access time
            self.domain_timestamps[domain] = time.time()

    async def _fetch_single(
        self,
        url: str,
        scroll_page: bool = True,
        max_retries: Optional[int] = None,
    ) -> Dict[str, str]:
        """Fetch the raw HTML content of a single URL with optimized resource handling."""
        if max_retries is None:
            max_retries = self.max_retries
            
        # Enforce rate limiting
        await self._enforce_domain_rate_limit(url)
            
        await self._ensure_browser_started()
        if not self.browser or not self.browser.is_connected():
            logger.error("Browser is not initialized or not connected.")
            return {
                "original_url": url,
                "final_url": url,
                "content": "",
                "error": "Browser initialization failed",
            }
            
        html_content = ""
        error_message = ""
        final_url = url
        fetch_start_time = time.time()
        
        # Use semaphore for concurrency control
        async with self.semaphore:
            logger.info(f"Starting fetch for {url}")
            context_item = None
            page = None
            
            for attempt in range(max_retries):
                try:
                    # Get a context from the pool
                    if not context_item:
                        context_item = await self._get_context_from_pool()
                    
                    # Create a new page in the context
                    page = await context_item["context"].new_page()
                    page.set_default_timeout(self.page_timeout)
                    
                    # Set performance optimizations for the page
                    await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}", 
                                     lambda route: route.abort())
                    
                    # Configure efficient page loading
                    await page.goto(url, 
                                   wait_until="domcontentloaded", 
                                   timeout=self.page_timeout)
                    final_url = page.url
                    
                    if scroll_page:
                        await self._scroll_page(page)

                    try:
                        # Shorter network idle timeout
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Network idle wait timed out for {final_url}. Continuing.")
                    except PlaywrightError as e:
                        logger.warning(f"Network idle wait failed for {final_url}: {e}. Continuing.")
                        
                    # Get HTML content efficiently
                    html_content = await page.content()

                    fetch_duration = time.time() - fetch_start_time
                    logger.info(
                        f"[Worker] Successfully fetched: {final_url} in {fetch_duration:.2f} seconds"
                    )
                    error_message = ""
                    break  # Success
                    
                except PlaywrightTimeoutError as e:
                    error_message = f"Timeout error for {url}: {str(e).splitlines()[0]}"
                    logger.error(f"{error_message} (Attempt {attempt+1}/{max_retries})")
                except PlaywrightError as e:
                    error_message = f"Playwright error for {url}: {str(e).splitlines()[0]}"
                    logger.error(f"{error_message} (Attempt {attempt+1}/{max_retries})")
                except Exception as e:
                    error_message = f"Unexpected error for {url}: {e}"
                    logger.error(f"{error_message} (Attempt {attempt+1}/{max_retries})")
                finally:
                    # Clean up page resources
                    if page:
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception as e:
                            logger.warning(f"Error closing page for {url}: {e}")
                        page = None
                
                # Handle retries with exponential backoff
                if attempt < max_retries - 1:
                    backoff = calculate_backoff(attempt)
                    logger.info(f"Retrying {url} in {backoff:.2f} seconds (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(backoff)
                    
            # Return context to pool
            if context_item:
                await self._return_context_to_pool(context_item)
                
            if error_message:
                fetch_duration = time.time() - fetch_start_time
                logger.error(
                    f"Failed to process {url} after {max_retries} attempts, took {fetch_duration:.2f} seconds."
                )
                
        result = {
            "original_url": url,
            "final_url": final_url,
            "content": html_content,
            "error": error_message,
        }
            
        return result

    async def _scroll_page(
        self, page: Page, scroll_delay: float = 0.3, max_scrolls: int = 5
    ):
        """More efficient scrolling implementation with adaptive timing."""
        try:
            last_height = await page.evaluate("document.body.scrollHeight")
            scroll_count = 0
            same_height_count = 0
            MAX_SAME_HEIGHT = 2
            
            while scroll_count < max_scrolls:
                # More efficient scrolling that avoids unnecessary script evaluation
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                
                # Adaptive scrolling delay
                await asyncio.sleep(scroll_delay)
                
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    same_height_count += 1
                    if same_height_count >= MAX_SAME_HEIGHT:
                        break
                else:
                    same_height_count = 0
                last_height = new_height
                scroll_count += 1
        except PlaywrightError as e:
            logger.warning(f"Scrolling failed for {page.url}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during scrolling for {page.url}: {e}")

    async def process_urls(
        self,
        urls: List[str],
        scroll_pages: bool = False,
        batch_size: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Process URLs in optimized batches with resource management.
        
        Args:
            urls: List of URLs to process
            scroll_pages: Whether to scroll pages during fetching
            batch_size: Optional batch size to process URLs in chunks
        """
        if not urls:
            return

        if not self.browser or not self.browser.is_connected():
            await self._ensure_browser_started()
            
        # Determine batch size if not provided
        if batch_size is None:
            batch_size = min(len(urls), self.semaphore._value * 2)
            
        # Process URLs in batches
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            tasks = [
                asyncio.create_task(
                    self._fetch_single(url, scroll_pages), 
                    name=f"fetch_{url[:50]}"
                )
                for url in batch
            ]
            
            # Process completed tasks
            for future in asyncio.as_completed(tasks):
                try:
                    result = await future
                    yield result
                    if result.get("error"):
                        logger.warning(
                            f"Error processing URL {result.get('original_url', 'unknown')}: {result['error']}"
                        )
                except Exception as e:
                    task_name = (
                        future.get_name() if hasattr(future, "get_name") else "unknown_task"
                    )
                    logger.error(
                        f"Task {task_name} raised an unexpected exception: {e}",
                        exc_info=True,
                    )
                    original_url = (
                        task_name.replace("fetch_", "")
                        if task_name.startswith("fetch_")
                        else "unknown_url"
                    )
                    yield {
                        "original_url": original_url,
                        "final_url": original_url,
                        "content": "",
                        "error": f"Task execution failed: {e}",
                    }
            
            # Small pause between batches to avoid overwhelming resources
            if i + batch_size < len(urls):
                await asyncio.sleep(0.5)


# ---- Resource Monitoring Utilities ----
class ResourceMonitor:
    """Utility to monitor system resources during crawling"""
    
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self._monitoring_task = None
        self._stop_event = asyncio.Event()
        self._stats = {
            "memory_usage": [],
            "cpu_usage": [],
        }
        
    async def start_monitoring(self):
        """Start monitoring resources"""
        self._stop_event.clear()
        self._monitoring_task = asyncio.create_task(self._monitor_resources())
        
    async def stop_monitoring(self):
        """Stop monitoring resources"""
        if self._monitoring_task:
            self._stop_event.set()
            await self._monitoring_task
            self._monitoring_task = None
            
    async def _monitor_resources(self):
        """Monitor system resources"""
        try:
            import psutil
        except ImportError:
            logger.warning("psutil not available, resource monitoring disabled")
            return
            
        while not self._stop_event.is_set():
            try:
                # Get current process
                process = psutil.Process()
                
                # Memory usage
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                self._stats["memory_usage"].append(memory_mb)
                
                # CPU usage
                cpu_percent = process.cpu_percent(interval=0.1)
                self._stats["cpu_usage"].append(cpu_percent)
                
                if len(self._stats["memory_usage"]) > 50:
                    # Keep only the last 50 measurements
                    self._stats["memory_usage"] = self._stats["memory_usage"][-50:]
                    self._stats["cpu_usage"] = self._stats["cpu_usage"][-50:]
                    
                # Log if memory usage is high
                if memory_mb > 500:  # More than 500MB
                    logger.warning(f"High memory usage: {memory_mb:.2f}MB")
                    
            except Exception as e:
                logger.error(f"Error monitoring resources: {e}")
                
            # Wait for next check
            try:
                await asyncio.wait_for(self._stop_event.wait(), self.check_interval)
            except asyncio.TimeoutError:
                pass
                
    def get_stats(self) -> Dict[str, List[float]]:
        """Get the collected stats"""
        return self._stats
        
    def get_summary(self) -> Dict[str, float]:
        """Get a summary of the stats"""
        memory_usage = self._stats["memory_usage"]
        cpu_usage = self._stats["cpu_usage"]
        
        return {
            "avg_memory_mb": sum(memory_usage) / max(1, len(memory_usage)),
            "max_memory_mb": max(memory_usage) if memory_usage else 0,
            "avg_cpu_percent": sum(cpu_usage) / max(1, len(cpu_usage)),
            "max_cpu_percent": max(cpu_usage) if cpu_usage else 0,
        }


# ---- Example Usage ----
async def main_playwright():
    """Example of using the PlaywrightCrawler with performance optimizations"""
    urls_to_fetch = [
        "https://hub.baai.ac.cn/",
        "https://www.jiqizhixin.com",
        "https://www.xinhuanet.com",
        "https://pro.jiqizhixin.com/reference/ff25ec2f-ffcf-4d75-9503-46ab55afc999",
    ]
    
    output_dir = "crawl_output_playwright_html"
    os.makedirs(output_dir, exist_ok=True)
    results_count = 0
    errors_count = 0
    
    # Create resource monitor
    resource_monitor = ResourceMonitor()
    await resource_monitor.start_monitoring()

    try:
        start_time = time.time()
        # Use the context manager for the crawler with optimized settings
        async with PlaywrightCrawler(
            headless=True, 
            max_concurrent_pages=4, 
            page_timeout=10000,
            browser_args={"args": ["--disable-dev-shm-usage", "--no-sandbox"]},
        ) as crawler:
            # Process URLs in batches with optimized parameters
            async for result in crawler.process_urls(
                urls=urls_to_fetch,
                scroll_pages=True,
                batch_size=2,  # Process in smaller batches for better stability
            ):
                results_count += 1
                print("-" * 40)
                print(f"Received result #{results_count}")
                print(f"Original URL: {result['original_url']}")
                
                if result["error"]:
                    errors_count += 1
                    print(f"Error: {result['error']}")
                else:
                    # Process the result
                    filename_part = (
                        result["original_url"]
                        .split("//")[-1]
                        .replace("/", "_")
                        .replace("?", "_")
                        .replace(":", "_")
                    )
                    filename = os.path.join(output_dir, f"{filename_part}.html")
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(f"<!-- Original URL: {result['original_url']} -->\n")
                            f.write(result["content"])
                        print(f"Output saved to: {filename}")
                    except Exception as write_err:
                        print(f"Error writing output file {filename}: {write_err}")
                    print(f"Content length: {len(result['content'])}")
                print("-" * 40)

        end_time = time.time()
        logger.info(f"Processing complete, took {end_time - start_time:.2f} seconds.")
        logger.info(
            f"Total results received: {results_count}, error count: {errors_count}"
        )
        
        # Print resource usage summary
        await resource_monitor.stop_monitoring()
        stats = resource_monitor.get_summary()
        logger.info(f"Resource usage summary:")
        logger.info(f"  Average memory usage: {stats['avg_memory_mb']:.2f}MB")
        logger.info(f"  Maximum memory usage: {stats['max_memory_mb']:.2f}MB")
        logger.info(f"  Average CPU usage: {stats['avg_cpu_percent']:.2f}%")
        logger.info(f"  Maximum CPU usage: {stats['max_cpu_percent']:.2f}%")

    except Exception as main_err:
        logger.exception("Error occurred in main execution block.")
        await resource_monitor.stop_monitoring()


async def main_aiohttp():
    """Example of using the AiohttpCrawler with performance optimizations"""
    urls_to_fetch = [
        "https://hub.baai.ac.cn/view/44762",
        "https://pro.jiqizhixin.com/reference/ff25ec2f-ffcf-4d75-9503-46ab55afc999",
        "http://www.news.cn/politics/20250409/c3d08c8507bc412ba22f174ac063bea9/c.html",
    ]
    
    # Create crawler with optimized settings
    crawler = AiohttpCrawler(
        max_concurrent_requests=5, 
        request_timeout=30,
        max_retries=3,
    )

    output_dir = "crawl_output_aiohttp_html"
    os.makedirs(output_dir, exist_ok=True)
    results_count = 0
    errors_count = 0
    
    # Create resource monitor
    resource_monitor = ResourceMonitor()
    await resource_monitor.start_monitoring()

    try:
        start_time = time.time()
        # Process URLs with batch size for better resource management
        async for result in crawler.process_urls(
            urls=urls_to_fetch,
            batch_size=3,
        ):
            results_count += 1
            print("-" * 40)
            print(f"Received result #{results_count}")
            print(f"Original URL: {result['original_url']}")
                
            if result["error"]:
                errors_count += 1
                print(f"Error: {result['error']}")
            else:
                # Process the result
                filename_part = (
                    result["original_url"]
                    .split("//")[-1]
                    .replace("/", "_")
                    .replace("?", "_")
                    .replace(":", "_")
                )
                filename = os.path.join(output_dir, f"{filename_part}.html")
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"<!-- Original URL: {result['original_url']} -->\n")
                        f.write(result["content"])
                    print(f"Output saved to: {filename}")
                except Exception as write_err:
                    print(f"Error writing output file {filename}: {write_err}")
                print(f"Content length: {len(result['content'])}")
            print("-" * 40)

        end_time = time.time()
        logger.info(f"Processing complete, took {end_time - start_time:.2f} seconds.")
        logger.info(
            f"Total results received: {results_count}, error count: {errors_count}"
        )
        
        # Print resource usage summary
        await resource_monitor.stop_monitoring()
        stats = resource_monitor.get_summary()
        logger.info(f"Resource usage summary:")
        logger.info(f"  Average memory usage: {stats['avg_memory_mb']:.2f}MB")
        logger.info(f"  Maximum memory usage: {stats['max_memory_mb']:.2f}MB")
        logger.info(f"  Average CPU usage: {stats['avg_cpu_percent']:.2f}%")
        logger.info(f"  Maximum CPU usage: {stats['max_cpu_percent']:.2f}%")

    except Exception as main_err:
        logger.exception("Error occurred in main execution block.")
        await resource_monitor.stop_monitoring()


if __name__ == "__main__":
    # Example of which crawler to run
    asyncio.run(main_playwright())
    # asyncio.run(main_aiohttp())
