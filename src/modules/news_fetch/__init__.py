#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资讯获取模块
负责从各类资讯源获取资讯内容
"""

from .news_fetcher import fetch_and_save_all

__all__ = ["fetch_and_save_all"]
