#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API客户端模块
负责与各种LLM API进行交互
"""

import logging
from typing import Dict, Any, Optional
import time
import requests
import json

# 导入API管理器
from src.utils.api_manager import api_manager

logger = logging.getLogger(__name__)


class LLMAPIClient:
    """LLM API客户端类，用于处理与各种LLM API的交互"""

    def __init__(self):
        """初始化LLM API客户端"""
        self.clients = {}

    def get_api_key(self, api_name: str) -> Optional[str]:
        """
        获取API密钥

        Args:
            api_name: API名称

        Returns:
            API密钥，如果不存在则返回None
        """
        return api_manager.get_api_key(api_name)

    def test_deepseek_connection(self, api_key: str) -> Dict[str, Any]:
        """
        测试DeepSeek API连接

        Args:
            api_key: DeepSeek API密钥

        Returns:
            结果字典，包含是否成功、响应内容和错误信息
        """
        url = "https://api.deepseek.com/chat/completions"
        payload = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello!"},
                ],
                "model": "deepseek-chat",
                "temperature": 0,
                "stream": True,
                "max_tokens": 2,
            }
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 加上响应时间
        start_time = time.time()
        try:
            with requests.request(
                "POST", url, headers=headers, data=payload
            ) as response:
                if response.status_code != 200:
                    raise Exception(f"API请求失败，状态码: {response.status_code}")
                for line in response.iter_lines():
                    if line:  # 检测到有数据流传输
                        return {
                            "success": True,
                            "response": "连接成功",
                            "latency": round(time.time() - start_time, 2),
                        }

        except Exception as e:
            logger.error(f"DeepSeek API请求失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

        return {"success": False, "error": "未知错误"}

    def call_deepseek(
        self,
        messages: list,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        调用DeepSeek API

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 采样温度
            max_tokens: 最大生成token数
            stream: 是否流式传输

        Returns:
            结果字典
        """
        api_key = self.get_api_key("deepseek")
        if not api_key:
            return {
                "success": False,
                "error": "未找到DeepSeek API密钥，请在设置页面配置",
            }

        url = "https://api.deepseek.com/chat/completions"
        payload = json.dumps(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "stream": stream,
                "max_tokens": max_tokens,
            }
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            if response.status_code == 200:
                return {"success": True, "text": response.text}

            # 处理常见错误码
            elif response.status_code == 400:
                return {
                    "success": False,
                    "error": "格式错误：请求体格式错误，请修改请求体。",
                }
            elif response.status_code == 401:
                return {"success": False, "error": "认证失败：API key 错误或认证失败。"}
            elif response.status_code == 402:
                return {"success": False, "error": "余额不足：请检查账户余额并充值。"}
            elif response.status_code == 422:
                return {
                    "success": False,
                    "error": "参数错误：请求体参数错误，请修改相关参数。",
                }
            elif response.status_code == 429:
                return {"success": False, "error": "请求速率达到上限：请降低请求频率。"}
            elif response.status_code == 500:
                return {"success": False, "error": "服务器内部故障：请稍后重试。"}
            elif response.status_code == 503:
                return {"success": False, "error": "服务器过载：请稍后重试。"}
            else:
                return {
                    "success": False,
                    "error": f"未知错误，状态码: {response.status_code}",
                }
        except Exception as e:
            logger.error(f"DeepSeek API请求失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    def test_api_connection(self, api_name: str, api_key: str) -> Dict[str, Any]:
        """
        测试API连接的通用方法

        Args:
            api_name: API名称，如"deepseek"、"openai"等
            api_key: API密钥

        Returns:
            结果字典，包含是否成功、响应内容和错误信息
        """
        try:
            if api_name.lower() == "deepseek":
                return self.test_deepseek_connection(api_key)
            else:
                return {"success": False, "error": f"不支持的API类型: {api_name}"}
        except Exception as e:
            logger.error(f"测试API连接失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}


# 创建单例实例
api_client = LLMAPIClient()
