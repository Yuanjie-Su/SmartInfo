#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库初始化模块
负责创建和初始化SQLite和ChromaDB数据库
"""

import os
import logging
import sqlite3
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# 默认数据库存储路径
DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
DEFAULT_SQLITE_DB_PATH = os.path.join(DEFAULT_DB_DIR, "smartinfo.db")
DEFAULT_CHROMA_DB_PATH = os.path.join(DEFAULT_DB_DIR, "chromadb")


def init_sqlite_db(db_path=None):
    """
    初始化SQLite数据库

    Args:
        db_path: 可选的SQLite数据库路径
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    try:
        # 确保数据目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 创建资讯表
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            publish_date TEXT,
            summary TEXT,
            content TEXT,
            analyzed BOOLEAN DEFAULT 0
        )
        """
        )

        # 创建资讯源表
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS news_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL
        )
        """
        )

        # 创建API配置表
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS api_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL UNIQUE,
            api_key TEXT NOT NULL
        )
        """
        )

        # 创建系统配置表
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE,
            config_value TEXT NOT NULL,
            description TEXT
        )
        """
        )

        # 创建用户问答历史表
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            context_ids TEXT
        )
        """
        )

        # 提交事务
        conn.commit()
        conn.close()

        logger.info(f"SQLite数据库初始化成功: {db_path}")
    except Exception as e:
        logger.error(f"SQLite数据库初始化失败: {str(e)}", exc_info=True)
        raise


def clear_news_data(db_path=None):
    """
    清除数据库中的资讯数据（news表），但保留news_sources表的数据

    Args:
        db_path: 可选的SQLite数据库路径

    Returns:
        bool: 清除成功返回True，否则返回False
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    try:
        # 确保数据库文件存在
        if not os.path.exists(db_path):
            logger.error(f"数据库文件不存在: {db_path}")
            return False

        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 清空news表数据
        cursor.execute("DELETE FROM news")

        # 重置自增ID
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='news'")

        # 提交更改
        conn.commit()
        conn.close()

        logger.info(f"已成功清除数据库中的资讯数据")
        return True
    except Exception as e:
        logger.error(f"清除资讯数据失败: {str(e)}", exc_info=True)
        return False


def init_chroma_db(chroma_db_path=None):
    """
    初始化ChromaDB向量数据库

    Args:
        chroma_db_path: 可选的ChromaDB数据库路径
    """
    if chroma_db_path is None:
        chroma_db_path = DEFAULT_CHROMA_DB_PATH

    try:
        # 确保数据目录存在
        os.makedirs(chroma_db_path, exist_ok=True)

        # 初始化ChromaDB客户端
        client = chromadb.PersistentClient(
            path=chroma_db_path,
            settings=Settings(
                anonymized_telemetry=False,  # 禁用遥测
            ),
        )

        # 创建或获取资讯集合
        news_collection = client.get_or_create_collection(
            name="news_collection", metadata={"description": "资讯内容的向量嵌入"}
        )

        logger.info(f"ChromaDB初始化成功: {chroma_db_path}")
    except Exception as e:
        logger.error(f"ChromaDB初始化失败: {str(e)}", exc_info=True)
        raise


def clear_chroma_data(chroma_db_path=None):
    """
    清除ChromaDB中的所有资讯向量数据

    Args:
        chroma_db_path: 可选的ChromaDB数据库路径

    Returns:
        bool: 清除成功返回True，否则返回False
    """
    if chroma_db_path is None:
        chroma_db_path = DEFAULT_CHROMA_DB_PATH

    try:
        # 确保数据目录存在
        if not os.path.exists(chroma_db_path):
            logger.error(f"ChromaDB数据库目录不存在: {chroma_db_path}")
            return False

        # 初始化ChromaDB客户端
        client = chromadb.PersistentClient(path=chroma_db_path)

        # 获取资讯集合并清空
        try:
            news_collection = client.get_collection("news_collection")
            news_collection.delete(where={})
            logger.info("ChromaDB资讯向量数据已清空")
        except Exception as e:
            logger.warning(f"清空ChromaDB集合时出错: {str(e)}")
            # 如果集合不存在，则忽略错误
            pass

        return True
    except Exception as e:
        logger.error(f"清除ChromaDB数据失败: {str(e)}", exc_info=True)
        return False


def init_news_sources(db_path=None):
    """
    初始化资讯源数据

    Args:
        db_path: 可选的SQLite数据库路径
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查是否已存在资讯源
        cursor.execute("SELECT COUNT(*) FROM news_sources")
        count = cursor.fetchone()[0]

        # 如果没有资讯源，则插入默认资讯源
        if count == 0:
            # 直接插入内置默认资讯源
            _insert_builtin_sources(cursor)
            conn.commit()
            logger.info("已成功初始化默认资讯源")

        conn.close()
    except Exception as e:
        logger.error(f"初始化资讯源数据失败: {str(e)}", exc_info=True)


def _insert_builtin_sources(cursor):
    """
    插入内置默认资讯源

    Args:
        cursor: 数据库游标

    Note:
        目前未配置任何默认资讯源。此方法保留作为未来可能添加默认资讯源使用。
    """
    # 当前时间
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 默认资讯源列表 - 这里保持为空列表，不添加任何默认资讯源
    default_sources = []

    # 插入默认资讯源
    for source in default_sources:
        cursor.execute(
            "INSERT INTO news_sources (name, url, category, last_modified) VALUES (?, ?, ?, ?)",
            (source["name"], source["url"], source["category"], now),
        )

    logger.info(f"成功插入 {len(default_sources)} 个内置默认资讯源")


def reset_news_sources(db_path=None):
    """
    重置资讯源数据，清空原有数据并从sources.json重新导入

    Args:
        db_path: 可选的SQLite数据库路径
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 清空资讯源表
        cursor.execute("DELETE FROM news_sources")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='news_sources'")
        conn.commit()

        # 重新导入资讯源
        init_news_sources(db_path)

        conn.close()
        logger.info("资讯源数据已重置")
    except Exception as e:
        logger.error(f"重置资讯源数据失败: {str(e)}", exc_info=True)


def reset_database(db_path=None, chroma_db_path=None):
    """
    重置整个数据库，删除所有表中的内容

    Args:
        db_path: 可选的SQLite数据库路径
        chroma_db_path: 可选的ChromaDB数据库路径
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    if chroma_db_path is None:
        chroma_db_path = DEFAULT_CHROMA_DB_PATH

    try:
        # 清空SQLite数据库表内容
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()

        # 清空所有表
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DELETE FROM {table_name}")
            logger.info(f"已清空表: {table_name}")

            # 重置自增ID
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}'")

        # 提交更改
        conn.commit()
        conn.close()

        # 清空ChromaDB数据
        clear_chroma_data(chroma_db_path)

        # 重新初始化默认资讯源
        init_news_sources(db_path)

        logger.info("数据库重置成功，并已初始化默认资讯源")
        return True
    except Exception as e:
        logger.error(f"重置数据库失败: {str(e)}", exc_info=True)
        return False


def init_databases(sqlite_db_path=None, chroma_db_path=None):
    """
    初始化所有数据库

    Args:
        sqlite_db_path: 可选的SQLite数据库路径
        chroma_db_path: 可选的ChromaDB数据库路径
    """
    if sqlite_db_path is None:
        sqlite_db_path = DEFAULT_SQLITE_DB_PATH

    if chroma_db_path is None:
        chroma_db_path = DEFAULT_CHROMA_DB_PATH

    # 初始化SQLite数据库
    init_sqlite_db(sqlite_db_path)

    # 初始化ChromaDB
    init_chroma_db(chroma_db_path)

    # 初始化资讯源
    init_news_sources(sqlite_db_path)

    logger.info("所有数据库初始化完成")


def run_migrations(db_path=None):
    """
    执行数据库迁移，确保数据库结构与最新版本一致

    Args:
        db_path: 可选的SQLite数据库路径
    """
    if db_path is None:
        db_path = DEFAULT_SQLITE_DB_PATH

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查news_sources表是否有parser_code列
        cursor.execute("PRAGMA table_info(news_sources)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # 如果没有parser_code列，添加它
        if "parser_code" not in column_names:
            logger.info("执行迁移: 向news_sources表添加parser_code列")
            cursor.execute("ALTER TABLE news_sources ADD COLUMN parser_code TEXT")
            conn.commit()
            logger.info("迁移完成: parser_code列已添加")

        # 如果没有type列，添加它并设置默认值为'rss'
        if "type" not in column_names:
            logger.info("执行迁移: 向news_sources表添加type列")
            cursor.execute(
                "ALTER TABLE news_sources ADD COLUMN type TEXT NOT NULL DEFAULT 'rss'"
            )
            conn.commit()
            logger.info("迁移完成: type列已添加，默认值为'rss'")

        # 删除旧的active_categories配置
        cursor.execute(
            "DELETE FROM system_config WHERE config_key = 'active_categories'"
        )
        if cursor.rowcount > 0:
            logger.info("执行迁移: 删除旧的active_categories配置")
            conn.commit()
            logger.info("迁移完成: 旧的active_categories配置已删除")

        conn.close()
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}", exc_info=True)
        raise
