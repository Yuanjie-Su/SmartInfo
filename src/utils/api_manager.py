#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API管理模块
负责管理API密钥配置和数据库交互
"""

import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# 导入数据库配置
from src.database.database import DEFAULT_SQLITE_DB_PATH

logger = logging.getLogger(__name__)

class APIManager:
    """API管理类，用于管理API密钥配置和数据库交互"""
    
    def __init__(self, db_path=None):
        """
        初始化API管理器
        
        Args:
            db_path: 可选的SQLite数据库路径
        """
        self.db_path = db_path if db_path else DEFAULT_SQLITE_DB_PATH
    
    def save_api_key(self, api_name: str, api_key: str) -> bool:
        """
        保存API密钥到数据库
        
        Args:
            api_name: API名称，如"deepseek"、"openai"等
            api_key: API密钥
            
        Returns:
            bool: 保存成功返回True，否则返回False
        """
        try:
            # 获取当前时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查是否已存在该API配置
            cursor.execute("SELECT id FROM api_config WHERE api_name = ?", (api_name,))
            result = cursor.fetchone()
            
            if result:
                # 更新现有配置
                cursor.execute(
                    "UPDATE api_config SET api_key = ?, modified_date = ? WHERE api_name = ?",
                    (api_key, now, api_name)
                )
                logger.info(f"已更新API密钥: {api_name}")
            else:
                # 插入新配置
                cursor.execute(
                    "INSERT INTO api_config (api_name, api_key, created_date, modified_date) VALUES (?, ?, ?, ?)",
                    (api_name, api_key, now, now)
                )
                logger.info(f"已添加新API密钥: {api_name}")
            
            # 提交事务
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"保存API密钥失败: {str(e)}", exc_info=True)
            return False
    
    def get_api_key(self, api_name: str) -> Optional[str]:
        """
        从数据库获取API密钥
        
        Args:
            api_name: API名称，如"deepseek"、"openai"等
            
        Returns:
            Optional[str]: API密钥，如果不存在则返回None
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询API密钥
            cursor.execute("SELECT api_key FROM api_config WHERE api_name = ?", (api_name,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                return result[0]
            else:
                logger.warning(f"未找到API密钥: {api_name}")
                return None
        except Exception as e:
            logger.error(f"获取API密钥失败: {str(e)}", exc_info=True)
            return None
    
    def delete_api_key(self, api_name: str) -> bool:
        """
        从数据库删除API密钥
        
        Args:
            api_name: API名称，如"deepseek"、"openai"等
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 删除API密钥
            cursor.execute("DELETE FROM api_config WHERE api_name = ?", (api_name,))
            
            # 提交事务
            conn.commit()
            conn.close()
            
            logger.info(f"已删除API密钥: {api_name}")
            return True
        except Exception as e:
            logger.error(f"删除API密钥失败: {str(e)}", exc_info=True)
            return False
    
    def list_api_keys(self) -> List[Tuple[str, str, str]]:
        """
        列出所有API密钥
        
        Returns:
            List[Tuple[str, str, str]]: API名称、创建时间和修改时间的列表
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询所有API配置
            cursor.execute("SELECT api_name, created_date, modified_date FROM api_config")
            results = cursor.fetchall()
            
            conn.close()
            
            return results
        except Exception as e:
            logger.error(f"列出API密钥失败: {str(e)}", exc_info=True)
            return []

# 创建单例实例
api_manager = APIManager() 