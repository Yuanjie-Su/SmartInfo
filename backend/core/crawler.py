# backend/core/crawler.py
# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time
import os
import functools
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

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

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
def calculate_backoff(
    attempt: int, base_delay: float = DEFAULT_RETRY_BASE_DELAY
) -> float:
    """Calculate exponential backoff with jitter"""
    delay = base_delay * (2**attempt)
    jitter = delay * DEFAULT_JITTER_FACTOR
    return delay + random.uniform(-jitter, jitter)


# --- Aiohttp Crawler Class ---


class AiohttpCrawler:
    """
    A crawler that uses aiohttp to asynchronously fetch web content.

    Can be used as an async context manager:

    async with AiohttpCrawler() as crawler:
        async for result in crawler.process_urls(urls):
            # Process result
    """

    def __init__(
        self,
        max_concurrent_requests: int = 10,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.max_concurrent_requests = max_concurrent_requests

        # --- create session ---

        # 1) Add user agent and headers
        user_agent = user_agent or "SmartInfo/1.0"
        headers = headers or {}
        if "User-Agent" not in headers and user_agent:
            headers["User-Agent"] = user_agent

        # 2) Add connection pooling settings
        tcp_connector = aiohttp.TCPConnector(
            limit=max_concurrent_requests,
            ttl_dns_cache=300,  # 5 minutes DNS cache TTL
            # enable_cleanup_closed=True, # fixed in python3.13
            force_close=False,  # Keep connections open for reuse
        )

        # 3) Create session with connection pooling
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=None),
            connector=tcp_connector,
        )

        # --- end of session creation ---

        # Track processed domains to implement per-domain rate limiting
        self.domain_timestamps = {}
        self.domain_locks: Dict[str, asyncio.Lock] = {}

        # semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def __aenter__(self):
        """Async enter method for context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager support."""
        await self.shutdown()
        return False  # Don't suppress exceptions

    async def shutdown(self):
        """Close the session and release all resources."""
        logger.info("Shutting down AiohttpCrawler...")
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                logger.info("Session closed successfully.")
            except Exception as e:
                logger.error(f"Error closing session: {e}")
        logger.info("AiohttpCrawler shutdown complete.")

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

    async def fetch_single(
        self,
        url: str,
        timeout: int = 10,
        max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
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
            while retry_attempt <= max_retries:
                try:
                    logger.info(f"[Worker] Fetching: {url} (Attempt {retry_attempt+1})")

                    # Improved request with proper timeout handling
                    async with self.session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        allow_redirects=True,
                        ssl=False,  # Skip SSL verification for better performance
                    ) as response:
                        response.raise_for_status()
                        final_url = str(response.url)

                        # Stream the content instead of loading it all at once
                        chunks = []
                        async for chunk in response.content.iter_chunked(8192):
                            chunks.append(chunk)

                        raw_content = b"".join(chunks)

                        # Attempt to decode the content more efficiently
                        encoding = response.charset
                        try:
                            if encoding:
                                html_content = raw_content.decode(
                                    encoding, errors="replace"
                                )
                            else:
                                # Use faster charset detection
                                matches = charset_normalizer.from_bytes(
                                    raw_content
                                ).best()
                                if matches:
                                    detected_encoding = matches.encoding
                                    html_content = raw_content.decode(
                                        detected_encoding, errors="replace"
                                    )
                                else:
                                    html_content = raw_content.decode(
                                        "utf-8", errors="replace"
                                    )

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
                    error_message = f"Request timed out (>{timeout} seconds)"
                    logger.error(f"Request timed out for {url}")
                except aiohttp.ClientError as e:
                    error_message = f"Client error: {e}"
                    logger.error(f"Client error for {url}: {e}")
                except Exception as e:
                    error_message = f"Unexpected error: {e}"
                    logger.exception(f"Unexpected error while fetching {url}")

                # Handle retries
                retry_attempt += 1
                if retry_attempt <= max_retries:
                    backoff = calculate_backoff(retry_attempt - 1)
                    logger.info(
                        f"Retrying {url} in {backoff:.2f} seconds (attempt {retry_attempt}/{max_retries})"
                    )
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
        timeout: int = 10,
        max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
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

        # Process URLs in batches for better resource management
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            tasks = [
                asyncio.create_task(
                    self.fetch_single(url, timeout, max_retries),
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
                    task_name = (
                        future.get_name()
                        if hasattr(future, "get_name")
                        else "unknown_task"
                    )
                    logger.error(
                        f"Task {task_name} raised an exception: {e}", exc_info=True
                    )

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
        user_agent_rotation: bool = True,
        max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
    ):
        self.headless = headless
        self.page_timeout = page_timeout
        self.max_retries = max_retries
        self.browser_args = browser_args or {}
        self.user_agent = user_agent
        self.user_agent_rotation = user_agent_rotation
        self.pw_instance: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._start_lock = asyncio.Lock()
        self._browser_initialized = False

        # Add performance optimizations
        self.context_pool = []
        self.context_pool_size = max_concurrent_pages
        self.context_pool_lock = asyncio.Lock()

        # Track processed domains to implement per-domain rate limiting
        self.domain_timestamps = {}
        self.domain_locks: Dict[str, asyncio.Lock] = {}

        # Initialize user agent list for rotation
        self.user_agents = self._initialize_user_agents(user_agent)

    async def __aenter__(self):
        """Async enter method for context manager support."""
        await self._ensure_browser_started()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager support."""
        await self.shutdown()
        return False  # Don't suppress exceptions

    def _initialize_user_agents(self, default_user_agent: Optional[str]) -> List[str]:
        """Initialize a list of user agents for rotation"""
        # Common user agents representing different browsers and devices
        common_user_agents = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
            # Safari on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36 Edg/90.0.818.51",
            # Chrome on Android
            "Mozilla/5.0 (Linux; Android 11; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
            # Safari on iOS
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Mobile/15E148 Safari/604.1",
        ]

        # If a default user agent is provided, add it to the beginning of the list
        if default_user_agent:
            return [default_user_agent] + common_user_agents

        # Use a custom user agent as the default if none is provided
        default = "SmartInfo/1.0 (Playwright)"
        return [default] + common_user_agents

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the list"""
        if not self.user_agent_rotation or len(self.user_agents) <= 1:
            return self.user_agents[0]

        return random.choice(self.user_agents)

    async def _initialize_context_pool(self):
        """Initialize a pool of browser contexts with diverse user agents for performance"""
        async with self.context_pool_lock:
            logger.info(
                f"Initializing context pool with {self.context_pool_size} contexts"
            )
            for i in range(self.context_pool_size):
                # Get a user agent - either the fixed one or a random one if rotation is enabled
                user_agent = self._get_random_user_agent()

                # Create device descriptor with a unique fingerprint
                viewport = {"width": 1280, "height": 720}
                if i % 3 == 1:  # Small variation in viewport sizes
                    viewport = {"width": 1366, "height": 768}
                elif i % 3 == 2:
                    viewport = {"width": 1920, "height": 1080}

                # Create a context with this user agent and viewport
                context = await self.browser.new_context(
                    user_agent=user_agent,
                    viewport=viewport,
                    java_script_enabled=True,
                    # Add a small amount of randomization to make each context slightly different
                    # locale=random.choice(["en-US", "en-GB", "en-CA"]),
                    # timezone_id=random.choice(["America/New_York", "Europe/London", "Asia/Shanghai"]),
                )

                # Store the user agent with the context
                self.context_pool.append(
                    {
                        "context": context,
                        "in_use": False,
                        "user_agent": user_agent,
                        "viewport": viewport,
                    }
                )

            logger.info("Context pool initialized with diverse browser profiles")

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

    async def _ensure_browser_started(self):
        """Use a lock to ensure Playwright and the browser are started (if not already running)."""
        # Quick check without acquiring the lock
        if self._browser_initialized and self.browser and self.browser.is_connected():
            return

        async with self._start_lock:
            # Double-check after acquiring the lock (double-checked locking pattern)
            if (
                self._browser_initialized
                and self.browser
                and self.browser.is_connected()
            ):
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

                # Set the initialization flag
                self._browser_initialized = True

            except Exception as e:
                await self.shutdown()
                raise RuntimeError(f"Unable to start browser: {e}") from e

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

    async def fetch_single(
        self,
        url: str,
        scroll_page: bool = False,
    ) -> Dict[str, str]:
        """Fetch the raw HTML content of a single URL with optimized resource handling."""
        # Enforce rate limiting
        await self._enforce_domain_rate_limit(url)

        # Only ensure browser is started if needed
        if (
            not self._browser_initialized
            or not self.browser
            or not self.browser.is_connected()
        ):
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

        logger.info(f"Starting fetch for {url}")
        context_item = None
        page = None

        for attempt in range(self.max_retries):
            try:
                # Get a context from the pool
                if not context_item:
                    context_item = await self._get_context_from_pool()

                # Create a new page in the context
                page = await context_item["context"].new_page()
                page.set_default_timeout(self.page_timeout)

                # Set performance optimizations for the page
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}",
                    lambda route: route.abort(),
                )

                # Configure efficient page loading
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.page_timeout
                )
                final_url = page.url

                if scroll_page:
                    await self._scroll_page(page)

                try:
                    # Shorter network idle timeout
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except PlaywrightTimeoutError:
                    logger.warning(
                        f"Network idle wait timed out for {final_url}. Continuing."
                    )
                except PlaywrightError as e:
                    logger.warning(
                        f"Network idle wait failed for {final_url}: {e}. Continuing."
                    )

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
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )
            except PlaywrightError as e:
                error_message = f"Playwright error for {url}: {str(e).splitlines()[0]}"
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )

                # Check for browser disconnection and try to recover
                if "Target closed" in str(e) or "Browser closed" in str(e):
                    logger.warning("Browser connection lost, attempting to recover...")
                    self._browser_initialized = False
                    try:
                        await self._ensure_browser_started()
                        context_item = None  # Force getting a new context
                    except Exception as init_err:
                        logger.error(f"Failed to recover browser: {init_err}")

            except Exception as e:
                error_message = f"Unexpected error for {url}: {e}"
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )
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
            if attempt < self.max_retries - 1:
                backoff = calculate_backoff(attempt)
                logger.info(
                    f"Retrying {url} in {backoff:.2f} seconds (attempt {attempt+1}/{self.max_retries})"
                )
                await asyncio.sleep(backoff)

        # Return context to pool
        if context_item:
            await self._return_context_to_pool(context_item)

        if error_message:
            fetch_duration = time.time() - fetch_start_time
            logger.error(
                f"Failed to process {url} after {self.max_retries} attempts, took {fetch_duration:.2f} seconds."
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
            batch_size = min(len(urls), self.context_pool_size * 2)

        # Process URLs in batches
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            tasks = [
                asyncio.create_task(
                    self.fetch_single(url, scroll_pages), name=f"fetch_{url[:50]}"
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
                        future.get_name()
                        if hasattr(future, "get_name")
                        else "unknown_task"
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


# ---- Selenium Crawler Class ----


class SeleniumCrawler:
    """
    A crawler that uses Selenium WebDriver to asynchronously fetch web content.
    Supports JavaScript rendered content with efficient resource management.

    Can be used as an async context manager:

    async with SeleniumCrawler() as crawler:
        async for result in crawler.process_urls(urls):
            # Process result
    """

    def __init__(
        self,
        headless: bool = True,
        max_concurrent_browsers: int = DEFAULT_MAX_CONCURRENT_REQUESTS // 2,
        page_timeout: int = 10,  # seconds
        browser_args: Optional[Dict[str, Any]] = None,
        user_agent: Optional[str] = None,
        user_agent_rotation: bool = True,
        max_retries: int = DEFAULT_MAX_RETRY_ATTEMPTS,
        chromedriver_path: Optional[str] = None,
    ):
        self.headless = headless
        self.page_timeout = page_timeout
        self.max_retries = max_retries
        self.browser_args = browser_args or {}
        self.user_agent = user_agent
        self.user_agent_rotation = user_agent_rotation
        self.chromedriver_path = chromedriver_path
        
        # Browser pool management
        self.driver_pool = []
        self.driver_pool_size = max_concurrent_browsers
        self.driver_pool_lock = asyncio.Lock()
        
        # Track processed domains to implement per-domain rate limiting
        self.domain_timestamps = {}
        self.domain_locks: Dict[str, asyncio.Lock] = {}
        
        # Initialize user agent list for rotation
        self.user_agents = self._initialize_user_agents(user_agent)
        
        # Driver initialization lock
        self._start_lock = asyncio.Lock()
    
    async def __aenter__(self):
        """Async enter method for context manager support."""
        await self._ensure_driver_pool_started()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager support."""
        await self.shutdown()
        return False  # Don't suppress exceptions
    
    def _initialize_user_agents(self, default_user_agent: Optional[str]) -> List[str]:
        """Initialize a list of user agents for rotation"""
        # Common user agents representing different browsers and devices
        common_user_agents = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
            # Safari on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36 Edg/90.0.818.51",
        ]
        
        # If a default user agent is provided, add it to the beginning of the list
        if default_user_agent:
            return [default_user_agent] + common_user_agents
            
        # Use a custom user agent as the default if none is provided
        default = "SmartInfo/1.0 (Selenium)"
        return [default] + common_user_agents
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the list"""
        if not self.user_agent_rotation or len(self.user_agents) <= 1:
            return self.user_agents[0]
            
        return random.choice(self.user_agents)
    
    def _create_chrome_options(self, user_agent: str = None) -> Options:
        """Create Chrome options with performance optimizations"""
        options = Options()
        
        if self.headless:
            options.add_argument("--headless=new")  # 新版Chrome中的无头模式
            
        # Add user agent if provided
        if user_agent:
            options.add_argument(f"user-agent={user_agent}")
            
        # Performance optimizations
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-infobars")
        
        # Disable images for faster loading
        options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.cookies": 2,
            },
        )
        
        # Add custom arguments if provided
        if self.browser_args:
            for arg in self.browser_args.get("args", []):
                options.add_argument(arg)
        
        return options
        
    async def _create_driver(self) -> webdriver.Chrome:
        """Create a new Chrome WebDriver instance asynchronously"""
        user_agent = self._get_random_user_agent()
        options = self._create_chrome_options(user_agent)
        
        # Use functools.partial to wrap the synchronous WebDriver initialization
        create_driver_func = functools.partial(
            webdriver.Chrome,
            options=options,
            service=Service(ChromeDriverManager().install() if not self.chromedriver_path else self.chromedriver_path)
        )
        
        # Execute the synchronous operation in a thread pool
        driver = await asyncio.to_thread(create_driver_func)
        
        # Set timeout
        driver.set_page_load_timeout(self.page_timeout)
        driver.implicitly_wait(self.page_timeout)
        
        return driver
        
    async def _ensure_driver_pool_started(self):
        """Ensure driver pool is initialized with at least one driver"""
        async with self._start_lock:
            if not self.driver_pool:
                logger.info(f"Initializing Selenium driver pool with {self.driver_pool_size} drivers")
                for _ in range(min(2, self.driver_pool_size)):  # Start with at least 2 drivers
                    try:
                        driver = await self._create_driver()
                        self.driver_pool.append({
                            "driver": driver,
                            "in_use": False,
                            "user_agent": self._get_random_user_agent(),
                        })
                    except Exception as e:
                        logger.error(f"Error creating WebDriver: {e}")
                        raise RuntimeError(f"Failed to initialize WebDriver: {e}")
    
    async def _get_driver_from_pool(self):
        """Get an available driver from the pool or create a new one if needed"""
        async with self.driver_pool_lock:
            # Try to find an available driver
            for item in self.driver_pool:
                if not item["in_use"]:
                    item["in_use"] = True
                    return item
                    
            # If all drivers are in use and we haven't reached the pool size limit, create a new one
            if len(self.driver_pool) < self.driver_pool_size:
                try:
                    driver = await self._create_driver()
                    new_item = {
                        "driver": driver,
                        "in_use": True,
                        "user_agent": self._get_random_user_agent(),
                    }
                    self.driver_pool.append(new_item)
                    return new_item
                except Exception as e:
                    logger.error(f"Error creating new driver: {e}")
                    raise RuntimeError(f"Failed to create new WebDriver: {e}")
            
            # If we've reached the pool size limit, wait for a driver to become available
            logger.info("All drivers in use, waiting for one to become available")
            # Find the first driver and use it (even though it's in use)
            # This is a fallback case and might cause concurrent driver usage issues
            for item in self.driver_pool:
                item["in_use"] = True
                return item
    
    async def _return_driver_to_pool(self, driver_item):
        """Return a driver to the pool"""
        async with self.driver_pool_lock:
            for item in self.driver_pool:
                if item["driver"] == driver_item["driver"]:
                    item["in_use"] = False
                    break
    
    async def _enforce_domain_rate_limit(self, url: str) -> None:
        """Enforce rate limiting per domain to avoid overloading servers"""
        domain = urlparse(url).netloc
        
        # Get or create a lock for this domain
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
    
    async def _scroll_page(self, driver, scroll_delay: float = 0.3, max_scrolls: int = 5):
        """Scroll the page to load dynamic content"""
        try:
            # Execute JavaScript scroll operation in the browser
            scroll_script = """
            function scrollDown() {
                window.scrollBy(0, window.innerHeight);
                return document.body.scrollHeight;
            }
            return scrollDown();
            """
            
            scroll_func = functools.partial(driver.execute_script, scroll_script)
            
            last_height = await asyncio.to_thread(scroll_func)
            scroll_count = 0
            same_height_count = 0
            MAX_SAME_HEIGHT = 2
            
            while scroll_count < max_scrolls:
                # Execute scroll and get new height
                new_height = await asyncio.to_thread(scroll_func)
                
                # Adaptive pause
                await asyncio.sleep(scroll_delay)
                
                if new_height == last_height:
                    same_height_count += 1
                    if same_height_count >= MAX_SAME_HEIGHT:
                        break
                else:
                    same_height_count = 0
                    
                last_height = new_height
                scroll_count += 1
                
        except Exception as e:
            logger.warning(f"Scrolling failed: {e}")
    
    async def fetch_single(
        self,
        url: str,
        scroll_page: bool = False,
    ) -> Dict[str, str]:
        """Fetch the raw HTML content of a single URL with Selenium WebDriver"""
        # Enforce rate limiting
        await self._enforce_domain_rate_limit(url)
        
        # Initialize result fields
        html_content = ""
        error_message = ""
        final_url = url
        fetch_start_time = time.time()
        
        # Ensure driver pool is started
        await self._ensure_driver_pool_started()
        
        driver_item = None
        
        for attempt in range(self.max_retries):
            try:
                # Get a driver from the pool
                if not driver_item:
                    driver_item = await self._get_driver_from_pool()
                
                driver = driver_item["driver"]
                
                # Use asyncio.to_thread to execute synchronous Selenium operations
                get_url_func = functools.partial(driver.get, url)
                await asyncio.to_thread(get_url_func)
                
                # Get the final URL (after any redirects)
                get_current_url_func = functools.partial(lambda: driver.current_url)
                final_url = await asyncio.to_thread(get_current_url_func)
                
                # Optionally scroll the page
                if scroll_page:
                    await self._scroll_page(driver)
                
                # Wait for page to load completely
                try:
                    wait_func = functools.partial(
                        WebDriverWait(driver, self.page_timeout).until,
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    await asyncio.to_thread(wait_func)
                except TimeoutException:
                    logger.warning(f"Timeout waiting for page to load: {url}")
                
                # Get the page source
                get_source_func = functools.partial(lambda: driver.page_source)
                html_content = await asyncio.to_thread(get_source_func)
                
                fetch_duration = time.time() - fetch_start_time
                logger.info(
                    f"[Worker] Successfully fetched: {final_url} in {fetch_duration:.2f} seconds"
                )
                error_message = ""
                break  # Success
                
            except TimeoutException as e:
                error_message = f"Timeout error for {url}: {e}"
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )
            except WebDriverException as e:
                error_message = f"WebDriver error for {url}: {str(e).splitlines()[0]}"
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )
                
                # Check for browser crash and try to recover
                if "chrome not reachable" in str(e).lower():
                    logger.warning("WebDriver connection lost, attempting to recover...")
                    # Close and remove the faulty driver
                    if driver_item:
                        try:
                            await asyncio.to_thread(driver_item["driver"].quit)
                        except:
                            pass  # Ignore quit errors on already crashed driver
                        
                        async with self.driver_pool_lock:
                            self.driver_pool = [item for item in self.driver_pool if item["driver"] != driver_item["driver"]]
                        
                        driver_item = None  # Force getting a new driver
                
            except Exception as e:
                error_message = f"Unexpected error for {url}: {e}"
                logger.error(
                    f"{error_message} (Attempt {attempt+1}/{self.max_retries})"
                )
            
            # Handle retries
            if attempt < self.max_retries - 1:
                backoff = calculate_backoff(attempt)
                logger.info(
                    f"Retrying {url} in {backoff:.2f} seconds (attempt {attempt+1}/{self.max_retries})"
                )
                await asyncio.sleep(backoff)
        
        # Return driver to pool
        if driver_item:
            await self._return_driver_to_pool(driver_item)
        
        if error_message:
            fetch_duration = time.time() - fetch_start_time
            logger.error(
                f"Failed to process {url} after {self.max_retries} attempts, took {fetch_duration:.2f} seconds."
            )
        
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
        scroll_pages: bool = False,
        batch_size: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Process a list of URLs and yield results containing raw HTML"""
        if not urls:
            return
        
        # Ensure driver pool is started
        await self._ensure_driver_pool_started()
        
        # Determine batch size if not provided
        if batch_size is None:
            batch_size = min(len(urls), self.driver_pool_size * 2)
        
        # Process URLs in batches
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            tasks = [
                asyncio.create_task(
                    self.fetch_single(url, scroll_pages), name=f"fetch_{url[:50]}"
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
                        future.get_name()
                        if hasattr(future, "get_name")
                        else "unknown_task"
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
            
            # Small pause between batches
            if i + batch_size < len(urls):
                await asyncio.sleep(0.5)
    
    async def shutdown(self):
        """Close all WebDriver instances and release resources."""
        logger.info("Shutting down SeleniumCrawler...")
        async with self._start_lock:
            if hasattr(self, "driver_pool") and self.driver_pool:
                for item in self.driver_pool:
                    try:
                        quit_func = functools.partial(item["driver"].quit)
                        await asyncio.to_thread(quit_func)
                        logger.info("WebDriver instance closed.")
                    except Exception as e:
                        logger.error(f"Error closing WebDriver: {e}")
                self.driver_pool = []
        logger.info("SeleniumCrawler shutdown complete.")
