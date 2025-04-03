#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库模块
负责创建和管理SQLite和ChromaDB数据库连接
采用单例模式确保连接只创建一次并在整个程序中复用
"""

import os
import logging
import sqlite3
import chromadb
import atexit
from threading import Lock
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# 默认数据库存储路径
DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
DEFAULT_SQLITE_DB_PATH = os.path.join(DEFAULT_DB_DIR, "smartinfo.db")
DEFAULT_CHROMA_DB_PATH = os.path.join(DEFAULT_DB_DIR, "chromadb")


class Database:
    """
    数据库管理类，采用单例模式

    确保在程序运行期间只创建一次数据库连接，并在程序结束时关闭连接
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, sqlite_db_path=None, chroma_db_path=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Database, cls).__new__(cls)
                    cls._instance._init_paths(sqlite_db_path, chroma_db_path)
                    cls._instance._sqlite_conn = None
                    cls._instance._chroma_client = None
                    cls._instance._initialize()
                    # 注册程序退出时的清理函数
                    atexit.register(cls._instance._cleanup)
        return cls._instance

    def _init_paths(self, sqlite_db_path, chroma_db_path):
        """初始化数据库路径"""
        self._sqlite_db_path = sqlite_db_path or DEFAULT_SQLITE_DB_PATH
        self._chroma_db_path = chroma_db_path or DEFAULT_CHROMA_DB_PATH

        # 确保数据目录存在
        os.makedirs(os.path.dirname(self._sqlite_db_path), exist_ok=True)
        os.makedirs(self._chroma_db_path, exist_ok=True)

    def _initialize(self):
        """初始化数据库连接和表结构"""
        try:
            # 初始化SQLite连接
            self._sqlite_conn = sqlite3.connect(
                self._sqlite_db_path, check_same_thread=False
            )
            self._create_sqlite_tables()

            # 初始化ChromaDB客户端
            self._chroma_client = chromadb.PersistentClient(
                path=self._chroma_db_path, settings=Settings(anonymized_telemetry=False)
            )
            self._init_chroma_collections()

            # 初始化默认资讯源
            self._init_news_sources()

            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}", exc_info=True)
            self._cleanup()  # 清理可能已创建的资源
            raise

    def _create_sqlite_tables(self):
        """创建SQLite数据库表"""
        cursor = self._sqlite_conn.cursor()

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
            category TEXT NOT NULL,
            parser_code TEXT,
            type TEXT NOT NULL DEFAULT 'rss'
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

        self._sqlite_conn.commit()

    def _init_chroma_collections(self):
        """初始化ChromaDB集合"""
        # 创建或获取资讯集合
        self._chroma_client.get_or_create_collection(
            name="news_collection", metadata={"description": "资讯内容的向量嵌入"}
        )

    def _init_news_sources(self):
        """初始化资讯源数据"""
        cursor = self._sqlite_conn.cursor()

        # 检查是否已存在资讯源
        cursor.execute("SELECT COUNT(*) FROM news_sources")
        count = cursor.fetchone()[0]

        # 如果没有资讯源，则插入默认资讯源
        if count == 0:
            # 目前未配置任何默认资讯源，此方法保留作为未来可能添加默认资讯源使用
            self._insert_builtin_sources(cursor)
            self._sqlite_conn.commit()
            logger.info("已成功初始化默认资讯源")

    def _insert_builtin_sources(self, cursor):
        """插入内置默认资讯源"""
        # 当前时间
        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 默认资讯源列表 - 这里保持为空列表，不添加任何默认资讯源
        default_sources = []

        # 插入默认资讯源
        for source in default_sources:
            cursor.execute(
                "INSERT INTO news_sources (name, url, category, type) VALUES (?, ?, ?, ?)",
                (
                    source["name"],
                    source["url"],
                    source["category"],
                    source.get("type", "rss"),
                ),
            )

        logger.info(f"成功插入 {len(default_sources)} 个内置默认资讯源")

    def _cleanup(self):
        """清理资源，关闭数据库连接"""
        try:
            if self._sqlite_conn:
                self._sqlite_conn.close()
                self._sqlite_conn = None
                logger.info("SQLite连接已关闭")
        except Exception as e:
            logger.error(f"关闭SQLite连接时出错: {str(e)}", exc_info=True)

    # 数据库操作方法
    def execute_query(self, query, params=(), fetch_all=False, commit=False):
        """
        执行SQL查询

        Args:
            query (str): SQL查询语句
            params (tuple): 查询参数
            fetch_all (bool): 是否获取所有结果
            commit (bool): 是否提交事务

        Returns:
            查询结果或受影响的行数
        """
        cursor = self._sqlite_conn.cursor()
        cursor.execute(query, params)

        result = None
        if fetch_all:
            result = cursor.fetchall()
        else:
            result = cursor.fetchone()

        if commit:
            self._sqlite_conn.commit()

        return result

    def execute_many(self, query, params_list, commit=True):
        """
        执行多条SQL语句

        Args:
            query (str): SQL查询语句
            params_list (list): 多组查询参数
            commit (bool): 是否提交事务

        Returns:
            受影响的行数
        """
        cursor = self._sqlite_conn.cursor()
        cursor.executemany(query, params_list)

        if commit:
            self._sqlite_conn.commit()

        return cursor.rowcount

    def get_chroma_collection(self, collection_name="news_collection"):
        """
        获取ChromaDB集合

        Args:
            collection_name (str): 集合名称

        Returns:
            ChromaDB集合对象
        """
        return self._chroma_client.get_collection(collection_name)

    # 数据库管理方法
    def clear_news_data(self):
        """
        清除数据库中的资讯数据（news表），但保留news_sources表的数据

        Returns:
            bool: 清除成功返回True，否则返回False
        """
        try:
            cursor = self._sqlite_conn.cursor()

            # 清空news表数据
            cursor.execute("DELETE FROM news")

            # 重置自增ID
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='news'")

            self._sqlite_conn.commit()
            logger.info("已成功清除数据库中的资讯数据")
            return True
        except Exception as e:
            logger.error(f"清除资讯数据失败: {str(e)}", exc_info=True)
            return False

    def clear_chroma_data(self):
        """
        清除ChromaDB中的所有资讯向量数据

        Returns:
            bool: 清除成功返回True，否则返回False
        """
        try:
            # 获取资讯集合并清空
            try:
                news_collection = self._chroma_client.get_collection("news_collection")
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

    def reset_news_sources(self):
        """
        重置资讯源数据，清空原有数据并重新初始化
        """
        try:
            cursor = self._sqlite_conn.cursor()

            # 清空资讯源表
            cursor.execute("DELETE FROM news_sources")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='news_sources'")
            self._sqlite_conn.commit()

            # 重新导入资讯源
            self._init_news_sources()

            logger.info("资讯源数据已重置")
        except Exception as e:
            logger.error(f"重置资讯源数据失败: {str(e)}", exc_info=True)

    def reset_database(self):
        """
        重置整个数据库，删除所有表中的内容

        Returns:
            bool: 重置成功返回True，否则返回False
        """
        try:
            cursor = self._sqlite_conn.cursor()

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
            self._sqlite_conn.commit()

            # 清空ChromaDB数据
            self.clear_chroma_data()

            # 重新初始化默认资讯源
            self._init_news_sources()

            logger.info("数据库重置成功，并已初始化默认资讯源")
            return True
        except Exception as e:
            logger.error(f"重置数据库失败: {str(e)}", exc_info=True)
            return False

    def run_migrations(self):
        """
        执行数据库迁移，确保数据库结构与最新版本一致
        """
        try:
            cursor = self._sqlite_conn.cursor()

            # 检查news_sources表结构
            cursor.execute("PRAGMA table_info(news_sources)")
            columns = cursor.fetchall()
            column_names = [column[1] for column in columns]

            # 执行必要的迁移
            # 如果将来有新的迁移需求，可以在这里添加

            # 删除旧的active_categories配置
            cursor.execute(
                "DELETE FROM system_config WHERE config_key = 'active_categories'"
            )
            if cursor.rowcount > 0:
                logger.info("执行迁移: 删除旧的active_categories配置")
                self._sqlite_conn.commit()
                logger.info("迁移完成: 旧的active_categories配置已删除")

        except Exception as e:
            logger.error(f"数据库迁移失败: {str(e)}", exc_info=True)
            raise


# 创建全局数据库实例
db = Database()

# 导出常用路径常量和数据库实例
__all__ = [
    "Database",
    "db",
    "DEFAULT_SQLITE_DB_PATH",
    "DEFAULT_CHROMA_DB_PATH",
]
