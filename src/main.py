#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SmartInfo - 智能资讯分析与知识管理工具
主程序入口
"""

import sys
import os
import logging
import argparse

# 添加项目根目录到Python模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from src.modules.ui.main_window import MainWindow
from src.database.db_init import init_databases
from src.config.config import init_config, get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("smartinfo.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="SmartInfo - 智能资讯分析与知识管理工具"
    )
    parser.add_argument("--reset-sources", action="store_true", help="重置资讯源数据")
    parser.add_argument("--clear-news", action="store_true", help="清除资讯数据")
    parser.add_argument("--reset-database", action="store_true", help="重置整个数据库")
    return parser.parse_args()


def main():
    """应用程序主入口"""
    try:
        # 解析命令行参数
        args = parse_args()

        # 初始化配置
        config = init_config()

        # 确保数据目录存在
        os.makedirs(config.get("data_dir"), exist_ok=True)

        # 初始化数据库
        db_path = os.path.join(config.get("data_dir"), "smartinfo.db")
        chroma_path = os.path.join(config.get("data_dir"), "chromadb")

        # 如果指定了重置整个数据库参数，则重置整个数据库
        if args.reset_database:
            from src.database.db_init import reset_database

            logger.info("正在重置数据库...")
            if reset_database(db_path, chroma_path):
                logger.info("数据库重置成功")
            else:
                logger.error("数据库重置失败")

        # 初始化数据库 (如果刚刚重置，也需要确保表结构正确)
        init_databases(db_path, chroma_path)

        # 如果指定了重置资讯源参数，则重置资讯源
        if args.reset_sources:
            from src.database.db_init import reset_news_sources

            logger.info("正在重置资讯源...")
            reset_news_sources(db_path)
            logger.info("资讯源重置完成")

        # 如果指定了清除资讯数据参数，则清除资讯数据
        if args.clear_news:
            from src.database.db_init import clear_news_data, clear_chroma_data

            logger.info("正在清除资讯数据...")
            if clear_news_data(db_path):
                logger.info("SQLite资讯数据清除成功")
            if clear_chroma_data(chroma_path):
                logger.info("向量数据库资讯数据清除成功")

        # 创建Qt应用
        app = QApplication(sys.argv)
        app.setApplicationName("SmartInfo")

        # 创建并显示主窗口
        window = MainWindow()
        window.show()

        # 启动应用事件循环
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"程序启动失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
