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
DEFAULT_DB_DIR = os.path.join(os.path.expanduser('~'), 'SmartInfo', 'data')
DEFAULT_SQLITE_DB_PATH = os.path.join(DEFAULT_DB_DIR, 'smartinfo.db')
DEFAULT_CHROMA_DB_PATH = os.path.join(DEFAULT_DB_DIR, 'chromadb')

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
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            publish_date TEXT NOT NULL,
            fetch_date TEXT NOT NULL,
            summary TEXT,
            content TEXT NOT NULL,
            analyzed BOOLEAN DEFAULT 0
        )
        ''')
        
        # 创建资讯源表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            active BOOLEAN DEFAULT 1
        )
        ''')
        
        # 创建API配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL UNIQUE,
            api_key TEXT NOT NULL,
            created_date TEXT NOT NULL,
            modified_date TEXT NOT NULL
        )
        ''')
        
        # 创建系统配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE,
            config_value TEXT NOT NULL,
            description TEXT,
            modified_date TEXT NOT NULL
        )
        ''')
        
        # 创建用户问答历史表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_date TEXT NOT NULL,
            context_ids TEXT
        )
        ''')
        
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
        client = chromadb.PersistentClient(path=chroma_db_path)
        
        # 创建或获取资讯集合
        news_collection = client.get_or_create_collection(
            name="news_collection",
            metadata={"description": "资讯内容的向量嵌入"}
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
        from ..config.config import get_config
        config = get_config()
        
        # 获取AI资讯分类
        categories = config.get("active_categories", ["学术动态", "AI工具应用", "前沿技术", "市场应用"])
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查是否已存在资讯源
        cursor.execute("SELECT COUNT(*) FROM news_sources")
        count = cursor.fetchone()[0]
        
        # 如果没有资讯源，则导入默认资讯源
        if count == 0:
            # 从sources.json加载资讯源
            import json
            import os
            
            # 获取sources.json文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            sources_file = os.path.join(current_dir, 'sources.json')
            
            # 加载资讯源
            with open(sources_file, 'r', encoding='utf-8') as f:
                sources = json.load(f)
                
            # 将资讯源插入数据库
            for source in sources:
                cursor.execute(
                    "INSERT INTO news_sources (name, url, type, category, active) VALUES (?, ?, ?, ?, ?)",
                    (source["name"], source["url"], source["type"], source["category"], source["active"])
                )
            
            conn.commit()
            logger.info(f"成功从sources.json导入 {len(sources)} 个默认资讯源")
        
        conn.close()
    except Exception as e:
        logger.error(f"初始化资讯源数据失败: {str(e)}", exc_info=True)

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