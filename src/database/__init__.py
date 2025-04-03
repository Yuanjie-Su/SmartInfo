#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库模块
负责数据库的创建、初始化和管理
"""

from .database import (
    Database,
    db,
    DEFAULT_SQLITE_DB_PATH,
    DEFAULT_CHROMA_DB_PATH,
)

__all__ = [
    "Database",
    "db",
    "DEFAULT_SQLITE_DB_PATH",
    "DEFAULT_CHROMA_DB_PATH",
]
