#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
项目配置模块
管理应用程序的全局配置
"""

import os
import json
import logging
import sqlite3
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AppConfig:
    """应用配置类"""

    # 默认配置
    DEFAULT_CONFIG = {
        # 数据存储路径
        "data_dir": os.path.join(os.path.expanduser("~"), "SmartInfo", "data"),
        # 资讯获取配置
        "fetch_frequency": "manual",  # manual, hourly, daily, weekly
        # API配置
        "api_provider": "deepseek",
        # 嵌入模型配置
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        # 界面配置
        "ui_theme": "light",  # light, dark
        "language": "zh_CN",
    }

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化配置

        Args:
            db_path: SQLite数据库路径，None则使用默认路径
        """
        # 配置字典
        self.config = self.DEFAULT_CONFIG.copy()

        # 设置数据库路径
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.path.join(self.config["data_dir"], "smartinfo.db")

        # 加载配置
        self._ensure_data_dir()
        self._load_from_db()

    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        os.makedirs(self.config["data_dir"], exist_ok=True)

    def _load_from_db(self) -> None:
        """从数据库加载配置"""
        # 如果数据库不存在，直接使用默认配置
        if not os.path.exists(self.db_path):
            logger.info("数据库不存在，使用默认配置")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 检查表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'"
            )
            if not cursor.fetchone():
                logger.info("配置表不存在，使用默认配置")
                conn.close()
                return

            # 加载配置
            cursor.execute("SELECT config_key, config_value FROM system_config")
            rows = cursor.fetchall()

            for key, value in rows:
                # 尝试将值解析为JSON对象
                try:
                    parsed_value = json.loads(value)
                    self.config[key] = parsed_value
                except json.JSONDecodeError:
                    # 如果不是JSON，则直接使用字符串值
                    self.config[key] = value

            conn.close()
            logger.info("成功从数据库加载配置")
        except Exception as e:
            logger.error(f"从数据库加载配置失败: {str(e)}", exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键
            default: 如果键不存在，返回的默认值

        Returns:
            配置值
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
        """
        self.config[key] = value

    def save(self) -> bool:
        """
        保存配置到数据库

        Returns:
            是否保存成功
        """
        try:
            # 确保数据目录存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 确保表存在
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT NOT NULL,
                description TEXT,
                modified_date TEXT NOT NULL
            )
            """
            )

            # 保存配置
            from datetime import datetime

            modified_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for key, value in self.config.items():
                # 将值转换为JSON字符串
                if (
                    isinstance(value, (dict, list, tuple, bool, int, float))
                    or value is None
                ):
                    json_value = json.dumps(value, ensure_ascii=False)
                else:
                    json_value = str(value)

                # 尝试更新，如果不存在则插入
                cursor.execute(
                    "INSERT OR REPLACE INTO system_config (config_key, config_value, modified_date) "
                    "VALUES (?, ?, ?)",
                    (key, json_value, modified_date),
                )

            conn.commit()
            conn.close()

            logger.info("成功保存配置到数据库")
            return True
        except Exception as e:
            logger.error(f"保存配置到数据库失败: {str(e)}", exc_info=True)
            return False

    def reset(self) -> None:
        """重置为默认配置"""
        self.config = self.DEFAULT_CONFIG.copy()


# 全局配置实例
config = None


def init_config(db_path: Optional[str] = None) -> AppConfig:
    """
    初始化全局配置

    Args:
        db_path: 数据库路径

    Returns:
        配置实例
    """
    global config
    if config is None:
        config = AppConfig(db_path)
    return config


def get_config() -> AppConfig:
    """
    获取全局配置实例

    Returns:
        配置实例
    """
    global config
    if config is None:
        config = init_config()
    return config
