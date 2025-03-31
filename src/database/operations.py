import sqlite3
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def load_news_sources(db_path: str) -> List[Dict]:
    """从数据库加载资讯源配置"""
    sources_list = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, url, category FROM news_sources")
        sources_data = cursor.fetchall()
        sources_list = [
            {"id": src[0], "name": src[1], "url": src[2], "category": src[3]}
            for src in sources_data
        ]
        conn.close()
        logger.info(f"Loaded {len(sources_list)} news sources from {db_path}")
    except Exception as e:
        logger.error(
            f"Failed to load news sources from {db_path}: {str(e)}", exc_info=True
        )
        # Optionally return default sources or raise the exception
    return sources_list


def save_news_item(
    db_path: str,
    title: str,
    url: str,
    source_name: str,
    category: str,
    publish_date: Optional[str] = None,
    summary: Optional[str] = None,
    content: Optional[str] = None,
) -> bool:
    """
    保存单条资讯到数据库，如果链接已存在则跳过。

    Args:
        db_path: 数据库路径
        title: 资讯标题
        url: 资讯链接 (用于检查重复)
        source_name: 资讯来源名称
        category: 资讯分类
        publish_date: 发布日期 (可选)
        summary: 资讯摘要 (可选)
        content: 资讯内容 (可选)
    Returns:
        True 如果成功保存, False 如果已存在或保存失败.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查资讯是否已存在
        cursor.execute("SELECT COUNT(*) FROM news WHERE link = ?", (url,))
        result = cursor.fetchone()

        if result[0] > 0:
            logger.debug(f"News item with link {url} already exists. Skipping.")
            conn.close()
            return False

        # 保存资讯
        cursor.execute(
            """
            INSERT INTO news (title, link, source, category, publish_date, summary, content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, url, source_name, category, publish_date, summary, content),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save news item {url}: {str(e)}", exc_info=True)
        # Rollback in case of error might be needed if not auto-committed
        if "conn" in locals() and conn:
            conn.rollback()  # Ensure rollback on error
            conn.close()
        return False


# Add other database operations as needed (e.g., update, delete)
