#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能问答模块
实现基于知识库的语义检索和问答功能
"""

import logging
import os
import json
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from sentence_transformers import SentenceTransformer
from datetime import datetime

logger = logging.getLogger(__name__)


class QAEngine:
    """智能问答引擎类"""

    def __init__(
        self,
        sqlite_path: str,
        chroma_path: str,
        api_key: str = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        """
        初始化智能问答引擎

        Args:
            sqlite_path: SQLite数据库路径
            chroma_path: ChromaDB向量数据库路径
            api_key: 大模型API密钥
            embedding_model: 嵌入模型名称
        """
        self.sqlite_path = sqlite_path
        self.chroma_path = chroma_path
        self.api_key = api_key
        self.embedding_model_name = embedding_model

        # 加载嵌入模型
        try:
            logger.info(f"初始化嵌入模型: {embedding_model}")
            self.embedding_model = SentenceTransformer(embedding_model)
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {str(e)}", exc_info=True)
            # 如果指定模型加载失败，尝试使用备用的小型模型
            try:
                backup_model = "sentence-transformers/paraphrase-MiniLM-L3-v2"
                logger.info(f"尝试加载备用模型: {backup_model}")
                self.embedding_model = SentenceTransformer(backup_model)
                self.embedding_model_name = backup_model
            except Exception as e2:
                logger.error(f"加载备用嵌入模型也失败: {str(e2)}", exc_info=True)
                raise

        # 连接向量数据库
        try:
            self.chroma_client = chromadb.PersistentClient(path=chroma_path)
            self.collection = self.chroma_client.get_or_create_collection(
                "news_collection"
            )
            logger.info("成功连接ChromaDB向量库")
        except Exception as e:
            logger.error(f"连接ChromaDB失败: {str(e)}", exc_info=True)
            raise

        # 如果未提供API密钥，尝试从数据库加载
        if not api_key:
            self._load_api_key()

    def _load_api_key(self) -> None:
        """从数据库加载API密钥"""
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            cursor.execute("SELECT api_key FROM api_config WHERE api_name = 'deepseek'")
            result = cursor.fetchone()

            if result:
                self.api_key = result[0]

            conn.close()
        except Exception as e:
            logger.error(f"加载API密钥失败: {str(e)}", exc_info=True)

    def check_and_update_embeddings(self) -> int:
        """
        检查并更新向量库中的内容

        Returns:
            更新的记录数量
        """
        try:
            # 从SQLite获取所有已分析但未添加到向量库的资讯
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            # 获取ChromaDB中已有的资讯ID列表
            existing_ids = set()
            try:
                all_ids = self.collection.get()["ids"]
                existing_ids = set(all_ids)
            except:
                pass

            # 查询已分析的资讯
            cursor.execute(
                "SELECT id, title, content, summary FROM news "
                "WHERE analyzed = 1 ORDER BY id"
            )

            to_add = []
            document_texts = []
            document_ids = []
            document_metadatas = []

            count = 0
            for row in cursor.fetchall():
                news_id = str(row[0])  # 转为字符串，ChromaDB要求ID为字符串

                # 检查是否已存在
                if news_id in existing_ids:
                    continue

                title = row[1]
                content = row[2]
                summary = row[3] or ""

                # 构建用于向量化的文本
                document_text = f"标题: {title}\n\n摘要: {summary}\n\n内容: {content}"

                # 构建元数据
                metadata = {
                    "title": title,
                    "summary": summary,
                    "content_preview": (
                        content[:200] + "..." if len(content) > 200 else content
                    ),
                }

                document_texts.append(document_text)
                document_ids.append(news_id)
                document_metadatas.append(metadata)
                count += 1

                # 批量处理，避免一次处理过多数据
                if count % 100 == 0:
                    if document_texts:
                        # 使用嵌入模型生成嵌入向量
                        embeddings = self.embedding_model.encode(
                            document_texts
                        ).tolist()

                        # 添加到ChromaDB
                        self.collection.add(
                            documents=document_texts,
                            embeddings=embeddings,
                            ids=document_ids,
                            metadatas=document_metadatas,
                        )

                        document_texts = []
                        document_ids = []
                        document_metadatas = []

            # 处理剩余的数据
            if document_texts:
                # 使用嵌入模型生成嵌入向量
                embeddings = self.embedding_model.encode(document_texts).tolist()

                # 添加到ChromaDB
                self.collection.add(
                    documents=document_texts,
                    embeddings=embeddings,
                    ids=document_ids,
                    metadatas=document_metadatas,
                )

            conn.close()
            logger.info(f"成功更新 {count} 条资讯到向量库")
            return count
        except Exception as e:
            logger.error(f"更新向量库失败: {str(e)}", exc_info=True)
            return 0

    def answer_question(
        self,
        question: str,
        use_history: bool = False,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        回答用户问题

        Args:
            question: 用户问题
            use_history: 是否使用历史对话
            history: 历史对话列表，每项包含'question'和'answer'

        Returns:
            包含答案和相关资讯的字典
        """
        try:
            # 检查问题是否为空
            if not question or not question.strip():
                return {
                    "answer": "请输入有效的问题",
                    "sources": [],
                    "error": "问题为空",
                }

            # 获取问题嵌入向量
            question_embedding = self.embedding_model.encode(question).tolist()

            # 从向量库中检索相关资讯
            search_results = self.collection.query(
                query_embeddings=[question_embedding],
                n_results=5,  # 获取前5条最相关的内容
                include=["documents", "metadatas", "distances"],
            )

            # 构建相关资料
            contexts = []
            sources = []
            if search_results and len(search_results["ids"][0]) > 0:
                for i in range(len(search_results["ids"][0])):
                    doc_id = search_results["ids"][0][i]
                    metadata = search_results["metadatas"][0][i]
                    distance = search_results["distances"][0][i]

                    # 相似度得分超过阈值才考虑
                    if distance < 0.7:  # 距离越小，相似度越高
                        contexts.append(search_results["documents"][0][i])
                        sources.append(
                            {
                                "id": doc_id,
                                "title": metadata.get("title", "未知标题"),
                                "preview": metadata.get("content_preview", ""),
                                "relevance": round(
                                    (1 - distance) * 100
                                ),  # 转换为0-100的相关度分数
                            }
                        )

            # 如果没有找到相关资料
            if not contexts:
                return {
                    "answer": "抱歉，我在知识库中找不到与您问题相关的信息。请尝试换一种问法，或者提供更多细节。",
                    "sources": [],
                    "error": "无相关资料",
                }

            # 构建提示词
            prompt = self._build_qa_prompt(
                question, contexts, history if use_history else None
            )

            # 调用大模型API
            answer = self._call_llm_api(prompt)

            if not answer:
                return {
                    "answer": "抱歉，生成回答时出现了问题。请稍后再试。",
                    "sources": sources,
                    "error": "API调用失败",
                }

            # 保存问答历史
            self._save_qa_history(question, answer, [src["id"] for src in sources])

            return {"answer": answer, "sources": sources, "error": None}
        except Exception as e:
            logger.error(f"回答问题失败: {str(e)}", exc_info=True)
            return {
                "answer": "处理您的问题时发生了错误。请稍后再试。",
                "sources": [],
                "error": str(e),
            }

    def get_qa_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取问答历史

        Args:
            limit: 最大获取数量

        Returns:
            问答历史列表
        """
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, question, answer, created_date, context_ids "
                "FROM qa_history ORDER BY created_date DESC LIMIT ?",
                (limit,),
            )

            history = []
            for row in cursor.fetchall():
                item = {
                    "id": row[0],
                    "question": row[1],
                    "answer": row[2],
                    "created_date": row[3],
                    "context_ids": row[4].split(",") if row[4] else [],
                }
                history.append(item)

            conn.close()
            return history
        except Exception as e:
            logger.error(f"获取问答历史失败: {str(e)}", exc_info=True)
            return []

    def clear_qa_history(self) -> bool:
        """
        清空问答历史

        Returns:
            是否清除成功
        """
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM qa_history")

            conn.commit()
            conn.close()

            logger.info("成功清空问答历史")
            return True
        except Exception as e:
            logger.error(f"清空问答历史失败: {str(e)}", exc_info=True)
            return False

    def _build_qa_prompt(
        self,
        question: str,
        contexts: List[str],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        构建问答提示词

        Args:
            question: 用户问题
            contexts: 相关上下文列表
            history: 历史对话列表

        Returns:
            提示词文本
        """
        prompt = "你是一个专业的资讯分析助手，基于以下参考资料回答用户的问题。\n\n"

        # 添加参考资料
        prompt += "参考资料:\n"
        for i, context in enumerate(contexts, 1):
            prompt += f"[{i}] {context}\n\n"

        # 添加历史对话
        if history:
            prompt += "历史对话:\n"
            for entry in history:
                prompt += f"用户: {entry['question']}\n"
                prompt += f"助手: {entry['answer']}\n\n"

        # 添加用户问题
        prompt += f"用户问题: {question}\n\n"

        # 添加回答指导
        prompt += "请基于上述参考资料回答用户问题。如果参考资料中没有相关信息，请明确告知，不要编造答案。回答要全面、准确、有条理，突出重点，并尽量使用自然、流畅的语言。"

        return prompt

    def _call_llm_api(self, prompt: str) -> Optional[str]:
        """
        调用大模型API

        Args:
            prompt: 提示词

        Returns:
            大模型返回的文本，失败时返回None
        """
        # 实际应用中需要替换为真实的API调用
        # 这里仅作为示例，模拟API调用
        try:
            logger.info("模拟调用大模型API...")

            # 在实际应用中，这里将调用LLM API
            # 示例：调用DeepSeek API
            """
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"API调用失败: {response.text}")
                return None
            """

            # 模拟返回结果
            return "这是一个模拟的回答。在实际应用中，这里将返回大模型基于知识库检索结果生成的回答。回答将根据检索到的相关资讯内容，针对用户问题给出准确、全面的解答。"
        except Exception as e:
            logger.error(f"调用大模型API失败: {str(e)}", exc_info=True)
            return None

    def _save_qa_history(
        self, question: str, answer: str, context_ids: List[str]
    ) -> bool:
        """
        保存问答历史

        Args:
            question: 问题
            answer: 回答
            context_ids: 相关资讯ID列表

        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            # 获取当前时间
            created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 将context_ids转换为逗号分隔的字符串
            context_ids_str = ",".join(context_ids) if context_ids else ""

            # 插入记录
            cursor.execute(
                "INSERT INTO qa_history (question, answer, created_date, context_ids) "
                "VALUES (?, ?, ?, ?)",
                (question, answer, created_date, context_ids_str),
            )

            conn.commit()
            conn.close()

            logger.info("成功保存问答记录")
            return True
        except Exception as e:
            logger.error(f"保存问答记录失败: {str(e)}", exc_info=True)
            return False
