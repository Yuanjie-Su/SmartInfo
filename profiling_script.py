#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Standalone script to profile the news fetching process using cProfile.
独立脚本，使用 cProfile 分析新闻获取过程的性能。
"""

import sys
import os
import logging
import asyncio
import cProfile
import pstats
import io
from typing import Dict, Any

# --- Project Setup ---
# Adjust the path if your script is located elsewhere relative to the src directory
# 如果你的脚本相对于 src 目录位于其他位置，请调整路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Assuming script is in project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, 'src') not in sys.path:
     sys.path.insert(0, os.path.join(project_root, 'src'))


# --- Early Imports (Config, Database, Repositories, Services, LLM Client) ---
# Ensure these imports match your project structure
# 确保这些导入与你的项目结构匹配
try:
    from src.config import init_config, get_config, AppConfig
    from src.db.connection import init_db_connection, get_db_connection_manager, DatabaseConnectionManager
    from src.db.repositories import (
        NewsRepository,
        NewsSourceRepository,
        NewsCategoryRepository,
        ApiKeyRepository,
        SystemConfigRepository,
        QARepository,
    )
    from src.services.llm_client import LLMClient
    from src.services.news_service import NewsService
    # Import other services if needed by NewsService initialization indirectly
    # 如果 NewsService 初始化间接需要，导入其他服务
except ImportError as e:
    print(f"Import Error: {e}. Please ensure the script is run from the correct directory"
          " and all project dependencies are installed.")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

# --- Configure Logging ---
# 配置日志
logging.basicConfig(
    level=logging.INFO, # Set to DEBUG for more details 设置为 DEBUG 获取更详细信息
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to console 输出到控制台
    ],
)
logger = logging.getLogger("ProfilingScript")

# --- Initialization Function ---
# 初始化函数
def initialize_app_for_profiling() -> Dict[str, Any]:
    """Initializes necessary components for profiling."""
    # 初始化配置
    logger.info("Initializing configuration...")
    config = init_config()

    # 初始化数据库连接
    logger.info("Initializing database connection...")
    db_manager = init_db_connection()

    # 初始化 LLM 客户端 (需要配置 API Key, e.g., in .env file)
    # (Requires API Key configuration, e.g., in .env file)
    logger.info("Initializing LLM client...")
    deepseek_api_key = config.get("API_KEY_DEEPSEEK") # Assumes config handles env/db loading
    if not deepseek_api_key:
         logger.warning("DeepSeek API key not found. LLM operations will fail.")
    llm_client = LLMClient(
        base_url="https://api.deepseek.com",
        api_key=deepseek_api_key,
        async_mode=True # Must be async for NewsService async methods 必须是异步模式
    )

    # 初始化 Repositories
    logger.info("Initializing repositories...")
    news_repo = NewsRepository()
    source_repo = NewsSourceRepository()
    category_repo = NewsCategoryRepository()

    # 初始化 NewsService
    logger.info("Initializing NewsService...")
    news_service = NewsService(news_repo, source_repo, category_repo, llm_client)

    return {"news_service": news_service}

# --- Main Profiling Logic ---
# 主要分析逻辑
async def profile_fetch_news(news_service: NewsService):
    """Runs the news fetching process to be profiled."""
    logger.info("Starting news fetch process for profiling...")
    # --- Call the function to profile ---
    # --- 调用需要分析的函数 ---
    # You can specify source_ids=None to fetch all, or provide a list of IDs
    # 你可以指定 source_ids=None 来获取所有源，或者提供一个 ID 列表
    saved_count = await news_service.fetch_news_from_sources(
        source_ids=None, # Example: Fetch all sources 示例：获取所有源
        on_item_saved=lambda item: logger.debug(f"Item saved (callback): {item.get('id')} - {item.get('title')}"),
        on_fetch_complete=lambda count: logger.info(f"Fetch complete (callback): {count} items saved.")
    )
    logger.info(f"Profiled fetch process finished. Total items saved: {saved_count}")

# --- Script Entry Point ---
# 脚本入口点
if __name__ == "__main__":
    logger.info("--- Starting Profiling Script ---")

    try:
        # Initialize 初始化
        services = initialize_app_for_profiling()
        news_service = services["news_service"]

        # --- Setup cProfile ---
        # --- 设置 cProfile ---
        profiler = cProfile.Profile()
        logger.info("Starting profiler...")
        profiler.enable()

        # --- Run the async function ---
        # --- 运行异步函数 ---
        # Use asyncio.run() to execute the main async logic
        # 使用 asyncio.run() 执行主要的异步逻辑
        asyncio.run(profile_fetch_news(news_service))

        # --- Stop cProfile and print stats ---
        # --- 停止 cProfile 并打印统计信息 ---
        profiler.disable()
        logger.info("Profiler stopped. Processing results...")

        # Create a stream to capture stats output 创建流以捕获统计输出
        s = io.StringIO()
        # Sort stats by cumulative time ('cumulative') or total time ('tottime')
        # 按累积时间 ('cumulative') 或总时间 ('tottime') 对统计信息进行排序
        stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        stats.print_stats(30) # Print top 30 functions 打印前 30 个函数

        # Print the captured stats 打印捕获的统计信息
        print("\n--- cProfile Results (Top 30 by Cumulative Time) ---")
        print(s.getvalue())
        print("----------------------------------------------------")

        # Optional: Save stats to a file for more detailed analysis (e.g., with snakeviz)
        # 可选：将统计信息保存到文件以进行更详细的分析（例如，使用 snakeviz）
        # stats_filename = "fetch_news_profile.prof"
        # profiler.dump_stats(stats_filename)
        # logger.info(f"Profile stats saved to {stats_filename}")
        # logger.info("You can visualize it using: snakeviz {stats_filename}")

    except RuntimeError as e:
         logger.error(f"RuntimeError: {e}", exc_info=True)
    except ImportError as e:
         # Already handled in initialize_app_for_profiling, but catch again just in case
         # 已在 initialize_app_for_profiling 中处理，但再次捕获以防万一
         logger.critical(f"Failed due to import error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        # Ensure DB connections are closed if atexit doesn't run properly in all scenarios
        # 确保在 atexit 在所有情况下未正常运行时关闭数据库连接
        try:
            db_manager = get_db_connection_manager()
            db_manager._cleanup() # Call cleanup explicitly if needed
        except Exception:
            pass # Ignore errors during cleanup
        logger.info("--- Profiling Script Finished ---")

