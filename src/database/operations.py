import logging
from typing import List, Dict, Optional
from .database import db  # 导入单例数据库实例

logger = logging.getLogger(__name__)


def load_news_sources() -> List[Dict]:
    """从数据库加载资讯源配置"""
    sources_list = []
    try:
        # 使用单例数据库实例执行查询
        result = db.execute_query(
            "SELECT id, name, url, category FROM news_sources", fetch_all=True
        )
        sources_list = [
            {"id": src[0], "name": src[1], "url": src[2], "category": src[3]}
            for src in result
        ]
        logger.info(f"加载了 {len(sources_list)} 个资讯源")
    except Exception as e:
        logger.error(f"加载资讯源失败: {str(e)}", exc_info=True)
        # 可选返回默认来源或引发异常
    return sources_list


def save_news_item(
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
        # 检查资讯是否已存在
        result = db.execute_query("SELECT COUNT(*) FROM news WHERE link = ?", (url,))

        if result[0] > 0:
            logger.debug(f"链接为 {url} 的资讯已存在，跳过。")
            return False

        # 保存资讯
        db.execute_query(
            """
            INSERT INTO news (title, link, source, category, publish_date, summary, content)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, url, source_name, category, publish_date, summary, content),
            commit=True,
        )
        return True
    except Exception as e:
        logger.error(f"保存资讯项 {url} 失败: {str(e)}", exc_info=True)
        return False


# 根据需要添加其他数据库操作 (例如，更新，删除)
