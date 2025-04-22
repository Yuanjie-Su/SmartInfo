#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Question and Answer Service Module
Implements simple Q&A functions by directly querying the LLM.
"""

import logging
from typing import List, Dict, Any, Optional

from src.db.repositories import QARepository

logger = logging.getLogger(__name__)

DEFAULT_QA_MODEL = "deepseek-chat"


class QAService:
    """Question and Answer Service Class"""

    def __init__(
        self,
        qa_repo: QARepository,
    ):
        self._qa_repo = qa_repo

    # --- Question Answering ---

    async def answer_question(
        self, question: str
    ) -> Dict[str, Any]:
        """
        Answers a user's question by directly querying the LLM.

        Args:
            question: The user's question.

        Returns:
            A dictionary containing the 'answer'.
            Includes an 'error' key if something went wrong.
        """
        if not question or not question.strip():
            return {
                "answer": "Please enter a valid question.",
                "error": "Empty question",
            }

        try:
            logger.info(f"Answering question directly via LLM: '{question}'")
            
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
                    "answer": "LLM API key not configured. Please check settings.",
                    "error": "API key missing",
                }
            
            # 按需创建 LLMClient 实例
            from src.services.llm_client import LLMClient
            
            # 1. 准备简单的提示词
            prompt = self._build_direct_qa_prompt(question)
            
            # 2. 使用上下文管理器创建并调用 LLM
            logger.debug("Creating temporary LLMClient and sending query...")
            async with LLMClient(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=volcengine_api_key,
                async_mode=True
            ) as llm_client:
                # 使用简化版的调用方式 - 也可以根据需要修改为不同的调用方式
                llm_response = await llm_client.get_completion_content(
                    model=DEFAULT_QA_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that answers questions clearly and concisely."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1024,
                    temperature=0.7,
                )
            
            # 3. 处理响应
            if llm_response and llm_response.strip():
                answer = llm_response.strip()
                logger.info(f"LLM Answer received: '{answer[:100]}...'")

                # 保存 Q&A 对到历史记录
                try:
                    self._qa_repo.add_qa(question, answer, "[]") # 将空列表作为JSON存储
                except Exception as db_err:
                    logger.error(f"Failed to save Q&A to history: {db_err}", exc_info=True)

                return {"answer": answer}
            else:
                error_msg = "Empty response from LLM"
                logger.error(f"LLM query failed: {error_msg}")
                return {
                    "answer": f"Sorry, an error occurred while answering the question: {error_msg}",
                    "error": error_msg,
                }

        except Exception as e:
            logger.error(f"Error during question answering: {e}", exc_info=True)
            return {
                "answer": f"An unexpected error occurred while processing your question.",
                "error": str(e),
            }

    def _build_direct_qa_prompt(self, question: str) -> str:
        """Builds a simple prompt to ask the LLM the question directly."""
        # You can customize this prompt further if needed
        return f"Please answer the following question directly:\n\nQuestion: {question}\n\nAnswer: "

    def get_qa_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves Q&A history from the database."""
        return self._qa_repo.get_all_qa(limit, offset)

    def clear_qa_history(self) -> bool:
        """Clears all Q&A history."""
        logger.warning("Clearing all Q&A history.")
        return self._qa_repo.clear_history()

    def delete_qa_entry(self, qa_id: int) -> bool:
        """Deletes a specific Q&A entry by its ID."""
        return self._qa_repo.delete_qa(qa_id)
