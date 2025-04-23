# src/db/repositories/chat_repository.py
# -*- coding: utf-8 -*-

import logging
import time
from typing import List, Dict, Any, Optional

from src.db.schema_constants import CHATS_TABLE
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChatRepository(BaseRepository):
    """Repository for chats table operations."""

    def create_chat(self, title: str = "新建聊天") -> Optional[int]:
        """创建一个新的聊天会话。"""
        now_timestamp = int(time.time())
        sql = f"""INSERT INTO {CHATS_TABLE} (title, created_at, updated_at)
                VALUES (?, ?, ?)"""
        params = (
            title,
            now_timestamp,
            now_timestamp,  # 初始创建时，updated_at 与 created_at 相同
        )

        query = self._execute(sql, params, commit=True)

        if query:
            last_id = self._get_last_insert_id(query)
            if last_id is not None:
                logger.info(f"Created new chat with ID {last_id}")
                return (
                    int(last_id)
                    if isinstance(last_id, (int, float)) or str(last_id).isdigit()
                    else None
                )
            else:
                logger.error("Failed to retrieve lastInsertId after creating chat.")
                return None
        else:
            logger.error("Failed to execute create chat.")
            return None

    def update_chat_title(self, chat_id: int, title: str) -> bool:
        """更新聊天标题。"""
        now_timestamp = int(time.time())
        sql = f"""UPDATE {CHATS_TABLE} 
                SET title = ?, updated_at = ?
                WHERE id = ?"""
        query = self._execute(sql, (title, now_timestamp, chat_id), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.info(f"Updated chat title for chat ID {chat_id}")
            else:
                logger.warning(f"No chat found with ID {chat_id} to update title")
            return updated
        return False

    def update_chat_timestamp(self, chat_id: int) -> bool:
        """更新聊天的时间戳（在添加新消息时调用）。"""
        now_timestamp = int(time.time())
        sql = f"""UPDATE {CHATS_TABLE} 
                SET updated_at = ?
                WHERE id = ?"""
        query = self._execute(sql, (now_timestamp, chat_id), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            updated = rows_affected > 0
            if updated:
                logger.debug(f"Updated timestamp for chat ID {chat_id}")
            else:
                logger.warning(f"No chat found with ID {chat_id} to update timestamp")
            return updated
        return False

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """获取指定ID的聊天信息。"""
        sql = f"""SELECT id, title, created_at, updated_at
                FROM {CHATS_TABLE}
                WHERE id = ?"""
        row = self._fetchone(sql, (chat_id,))

        if row:
            return {
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
        return None

    def get_all_chats(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有聊天记录，按更新时间倒序排列。"""
        sql = f"""SELECT id, title, created_at, updated_at
                FROM {CHATS_TABLE}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?"""
        rows = self._fetchall(sql, (limit, offset))

        chats = []
        for row in rows:
            chats.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "updated_at": row[3],
                }
            )
        return chats

    def delete_chat(self, chat_id: int) -> bool:
        """删除指定ID的聊天及其所有消息（通过外键级联删除）。"""
        sql = f"DELETE FROM {CHATS_TABLE} WHERE id = ?"
        query = self._execute(sql, (chat_id,), commit=True)

        if query:
            rows_affected = self._get_rows_affected(query)
            deleted = rows_affected > 0
            if deleted:
                logger.info(f"Deleted chat with ID {chat_id}")
            else:
                logger.warning(f"No chat found with ID {chat_id} to delete")
            return deleted
        return False

    def clear_all_chats(self) -> bool:
        """删除所有聊天记录。"""
        logger.warning("Attempting to clear all chats")

        # 开始事务
        if not self._db.transaction():
            logger.error("Failed to start transaction for clear_all_chats")
            return False

        # 删除所有聊天记录
        query_del = self._execute(f"DELETE FROM {CHATS_TABLE}", commit=False)
        query_seq = self._execute(
            f"DELETE FROM sqlite_sequence WHERE name=?",
            (CHATS_TABLE,),
            commit=False,
        )

        cleared = query_del is not None and query_seq is not None

        if cleared:
            if not self._db.commit():
                logger.error(
                    f"Failed to commit transaction for clear_all_chats: {self._db.lastError().text()}"
                )
                self._db.rollback()
                cleared = False
            else:
                logger.info(f"Cleared all data from {CHATS_TABLE} table")
        else:
            logger.error(f"Failed to clear chats from {CHATS_TABLE}. Rolling back.")
            self._db.rollback()

        return cleared
