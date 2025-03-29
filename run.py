#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SmartInfo - 智能资讯分析与知识管理工具
启动脚本
"""

import os
import sys
import subprocess


def main():
    """
    启动SmartInfo应用程序
    """
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 设置Python模块搜索路径
    sys.path.insert(0, current_dir)

    # 启动命令，传递所有命令行参数
    cmd = [sys.executable, os.path.join(current_dir, "src", "main.py")]
    cmd.extend(sys.argv[1:])  # 添加所有命令行参数

    print("正在启动SmartInfo...")
    print(f"执行命令: {' '.join(cmd)}")

    # 启动程序
    process = subprocess.Popen(cmd)
    process.wait()


if __name__ == "__main__":
    main()
