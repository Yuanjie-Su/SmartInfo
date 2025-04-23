#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Service Module
Implements chat functionality using the new database structure.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from src.db.repositories import ChatRepository, MessageRepository

logger = logging.getLogger(__name__)

DEFAULT_QA_MODEL = "deepseek-chat"


class ChatService:
    """Chat Service Class"""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
    ):
        self._chat_repo = chat_repo
        self._message_repo = message_repo

    # --- Chat Management ---

    def create_chat(self, title: str = "新建聊天") -> Optional[Dict[str, Any]]:
        """
        创建一个新的聊天会话。

        Args:
            title: 聊天标题，默认为"新建聊天"

        Returns:
            包含新创建聊天信息的字典，如果创建失败则返回None
        """
        chat_id = self._chat_repo.create_chat(title)
        if chat_id is not None:
            return self._chat_repo.get_chat(chat_id)
        return None

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        获取指定ID的聊天信息，包括消息内容。

        Args:
            chat_id: 聊天ID

        Returns:
            包含聊天信息和消息内容的字典，如果不存在则返回None
        """
        chat = self._chat_repo.get_chat(chat_id)
        if not chat:
            return None

        # 获取聊天中的所有消息
        messages = self._message_repo.get_messages(chat_id)
        chat["messages"] = messages

        return chat

    def update_chat_title(self, chat_id: int, title: str) -> bool:
        """
        更新聊天标题。

        Args:
            chat_id: 聊天ID
            title: 新标题

        Returns:
            更新是否成功
        """
        return self._chat_repo.update_chat_title(chat_id, title)

    def delete_chat(self, chat_id: int) -> bool:
        """
        删除指定ID的聊天及其所有消息。

        Args:
            chat_id: 聊天ID

        Returns:
            删除是否成功
        """
        return self._chat_repo.delete_chat(chat_id)

    def clear_all_chats(self) -> bool:
        """
        清空所有聊天记录。

        Returns:
            操作是否成功
        """
        return self._chat_repo.clear_all_chats()

    # --- Message Management ---

    def add_message(
        self, chat_id: int, sender: str, content: str
    ) -> Optional[Dict[str, Any]]:
        """
        添加一条消息到指定聊天。

        Args:
            chat_id: 聊天ID
            sender: 发送者，如 "You" 或 "Assistant"
            content: 消息内容

        Returns:
            新添加的消息信息，如果添加失败则返回None
        """
        message_id = self._message_repo.add_message(chat_id, sender, content)
        if message_id is None:
            return None

        # 更新聊天的时间戳
        self._chat_repo.update_chat_timestamp(chat_id)

        return self._message_repo.get_message(message_id)

    def get_messages(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        获取指定聊天的所有消息。

        Args:
            chat_id: 聊天ID

        Returns:
            消息列表
        """
        return self._message_repo.get_messages(chat_id)

    def delete_message(self, message_id: int) -> bool:
        """
        删除指定ID的消息。

        Args:
            message_id: 消息ID

        Returns:
            删除是否成功
        """
        return self._message_repo.delete_message(message_id)

    # --- Chat Listing and Grouping ---

    def get_all_chats(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取所有聊天会话，并按更新时间排序。

        Args:
            limit: 返回数量限制
            offset: 分页偏移量

        Returns:
            聊天列表
        """
        chats = self._chat_repo.get_all_chats(limit, offset)

        # 为每个聊天添加最后一条消息的预览
        for chat in chats:
            last_messages = self._message_repo.get_chat_last_messages(chat["id"], 1)
            if last_messages:
                chat["last_message"] = last_messages[0]
            else:
                chat["last_message"] = None

        return chats

    def get_grouped_chats(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取分组后的聊天会话，按 Today、Yesterday、Others 分组。

        Returns:
            按日期分组的聊天字典
        """
        # 获取所有聊天
        all_chats = self.get_all_chats(limit=100)  # 适当限制数量

        # 计算日期界限
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # 初始化分组
        grouped_chats = {"Today": [], "Yesterday": [], "Others": []}

        # 对聊天进行分组
        for chat in all_chats:
            try:
                # 尝试解析聊天创建时间
                chat_date_str = chat.get("created_at") or chat.get("updated_at")
                if not chat_date_str:
                    # 如果没有时间信息，放入Others组
                    grouped_chats["Others"].append(chat)
                    continue

                chat_date = datetime.fromisoformat(chat_date_str).date()

                # 根据日期分组
                if chat_date == today:
                    grouped_chats["Today"].append(chat)
                elif chat_date == yesterday:
                    grouped_chats["Yesterday"].append(chat)
                else:
                    grouped_chats["Others"].append(chat)
            except (ValueError, TypeError):
                # 日期解析错误，放入Others组
                grouped_chats["Others"].append(chat)

        return grouped_chats

    # --- Question Answering ---

    async def answer_question(
        self, question: str, chat_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        回答问题并将问答对存储到聊天记录中。

        Args:
            question: 用户问题
            chat_id: 可选的聊天ID，如果提供则添加到现有聊天，否则创建新聊天

        Returns:
            包含回答和聊天信息的字典
        """
        if not question or not question.strip():
            return {
                "answer": "请输入有效的问题。",
                "error": "空问题",
            }

        try:
            logger.info(f"通过LLM回答问题: '{question}'")

            # 获取API key
            from src.services.setting_service import SettingService
            from src.config import init_config
            from src.db.repositories import ApiKeyRepository, SystemConfigRepository

            config = init_config()
            api_key_repo = ApiKeyRepository()
            system_config_repo = SystemConfigRepository()
            setting_service = SettingService(config, api_key_repo, system_config_repo)
            volcengine_api_key = setting_service.get_api_key("volcengine")

            if not volcengine_api_key:
                return {
                    "answer": "LLM API key未配置。请检查设置。",
                    "error": "API key缺失",
                }

            # 创建LLMClient实例
            from src.services.llm_client import LLMClient

            # 准备提示词
            prompt = self._build_direct_qa_prompt(question)

            # 使用上下文管理器创建并调用LLM
            logger.debug("创建临时LLMClient并发送查询...")
            async with LLMClient(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=volcengine_api_key,
                async_mode=True,
            ) as llm_client:
                llm_response = await llm_client.get_completion_content(
                    model=DEFAULT_QA_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that answers questions clearly and concisely.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.7,
                )

            # 处理响应
            if llm_response and llm_response.strip():
                answer = llm_response.strip()
                logger.info(f"收到LLM回答: '{answer[:100]}...'")

                # 处理存储聊天记录
                result = {"answer": answer}

                # 如果没有提供聊天ID，创建一个新聊天
                if chat_id is None:
                    # 使用问题的前30个字符作为聊天标题
                    title = question[:30] + ("..." if len(question) > 30 else "")
                    new_chat = self.create_chat(title)
                    if new_chat:
                        chat_id = new_chat["id"]
                        result["chat_id"] = chat_id
                        result["is_new_chat"] = True
                    else:
                        logger.error("创建新聊天失败")
                        return {
                            "answer": answer,
                            "error": "无法创建新聊天",
                        }
                else:
                    # 使用现有聊天
                    result["chat_id"] = chat_id
                    result["is_new_chat"] = False

                # 保存用户问题
                user_message = self.add_message(chat_id, "You", question)
                if not user_message:
                    logger.error(f"将用户问题添加到聊天 {chat_id} 失败")

                # 保存LLM回答
                assistant_message = self.add_message(chat_id, "Assistant", answer)
                if not assistant_message:
                    logger.error(f"将助手回答添加到聊天 {chat_id} 失败")

                # 如果提供了旧的QA存储库，也保存一份（向后兼容）
                if self._qa_repo:
                    try:
                        self._qa_repo.add_qa(question, answer, "[]")
                    except Exception as db_err:
                        logger.error(
                            f"保存Q&A到旧历史记录失败: {db_err}", exc_info=True
                        )

                return result
            else:
                error_msg = "LLM返回空响应"
                logger.error(f"LLM查询失败: {error_msg}")
                return {
                    "answer": f"抱歉，回答问题时出错: {error_msg}",
                    "error": error_msg,
                }

        except Exception as e:
            logger.error(f"问答过程中出错: {e}", exc_info=True)
            return {
                "answer": f"处理您的问题时发生意外错误。",
                "error": str(e),
            }

    def _build_direct_qa_prompt(self, question: str) -> str:
        """构建提示词以直接向LLM提问。"""
        return f"请直接回答以下问题:\n\n问题: {question}\n\n回答: "
