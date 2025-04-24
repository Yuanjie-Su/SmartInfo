# src/db/repositories/message_repository.py
# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from src.db.schema_constants import MESSAGES_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository):
    """Repository for messages table operations."""

    def add_message(self, chat_id: int, sender: str, content: str) -> Optional[int]:
        """添加一条新消息到特定聊天会话。"""
        # 获取当前聊天中的最大序列号
        max_seq = self._get_max_sequence_number(chat_id)
        sequence_number = max_seq + 1

        now_str = datetime.now().isoformat()
        sql = f"""INSERT INTO {MESSAGES_TABLE} (chat_id, sender, content, timestamp, sequence_number)
                VALUES (?, ?, ?, ?, ?)"""
        params = (chat_id, sender, content, now_str, sequence_number)

        query = self._execute(sql, params, commit=True)

        if query:
            last_id = self._get_last_insert_id(query)
            if last_id is not None:
                logger.info(f"Added message with ID {last_id} to chat {chat_id}")
                return (
                    int(last_id)
                    if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                    else None
                )
            else:
                logger.error("Failed to retrieve lastInsertId after adding message.")
                return None
        else:
            logger.error(f"Failed to execute add message to chat {chat_id}.")
            return None

    def _get_max_sequence_number(self, chat_id: int) -> int:
        """获取特定聊天中的最大序列号。"""
        sql = f"""SELECT MAX(sequence_number) FROM {MESSAGES_TABLE}
                WHERE chat_id = ?"""
        row = self._fetchone(sql, (chat_id,))

        if row and row[0] is not None:
            try:
                # 尝试将结果转换为整数
                return int(row[0])
            except (ValueError, TypeError):
                # 如果转换失败（虽然理论上 MAX 应该返回数字或 None），记录错误并返回 0
                logger.error(
                    f"Failed to convert max sequence number '{row[0]}' to int for chat_id {chat_id}. Returning 0."
                )
                return 0
        else:
            # 如果没有找到记录 (row is None) 或者 MAX 结果是 NULL (row[0] is None)，
            # 表示这是该聊天的第一条消息，最大序号视为 0
            return 0

    def get_messages(self, chat_id: int) -> List[Dict[str, Any]]:
        """获取特定聊天会话的所有消息，按序列号排序。"""
        sql = f"""SELECT id, chat_id, sender, content, timestamp, sequence_number
                FROM {MESSAGES_TABLE}
                WHERE chat_id = ?
                ORDER BY sequence_number ASC"""
        rows = self._fetchall(sql, (chat_id,))

        messages = []
        for row in rows:
            messages.append(
                {
                    "id": row[0],
                    "chat_id": row[1],
                    "sender": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                    "sequence_number": row[5],
                }
            )
        return messages

    def get_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """获取指定ID的消息。"""
        sql = f"""SELECT id, chat_id, sender, content, timestamp, sequence_number
                FROM {MESSAGES_TABLE}
                WHERE id = ?"""
        row = self._fetchone(sql, (message_id,))

        if row:
            return {
                "id": row[0],
                "chat_id": row[1],
                "sender": row[2],
                "content": row[3],
                "timestamp": row[4],
                "sequence_number": row[5],
            }
        return None

    def delete_message(self, message_id: int) -> bool:
        """删除指定ID的消息。"""
        sql = f"DELETE FROM {MESSAGES_TABLE} WHERE id = ?"
        query = self._execute(sql, (message_id,), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted message with ID {message_id}")
            else:
                logger.warning(f"No message found with ID {message_id} to delete")
            return deleted
        return False

    def delete_chat_messages(self, chat_id: int) -> bool:
        """删除特定聊天会话的所有消息。"""
        sql = f"DELETE FROM {MESSAGES_TABLE} WHERE chat_id = ?"
        query = self._execute(sql, (chat_id,), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted all messages for chat ID {chat_id}")
            else:
                logger.debug(f"No messages found for chat ID {chat_id} to delete")
            return True  # 即使没有删除任何行，也认为操作成功
        return False

    def update_message_content(self, message_id: int, content: str) -> bool:
        """更新指定消息ID的内容。

        Args:
            message_id: 消息ID
            content: 新的消息内容

        Returns:
            更新是否成功
        """
        sql = f"UPDATE {MESSAGES_TABLE} SET content = ? WHERE id = ?"
        query = self._execute(sql, (content, message_id), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.debug(f"Updated content for message ID {message_id}")
            else:
                logger.warning(f"No message found with ID {message_id} to update")
            return updated
        return False
