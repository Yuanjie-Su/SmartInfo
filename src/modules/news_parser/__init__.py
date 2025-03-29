#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
动态网页内容解析器模块
负责动态解析网页内容，从数据库获取解析代码并执行
"""

from .dynamic_parser import dynamic_parser

__all__ = ['dynamic_parser']