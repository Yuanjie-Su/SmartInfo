#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能分析模块
负责调用大模型API对资讯内容进行分析与摘要生成
"""

import logging
import json
import sqlite3
from typing import Dict, Any, Optional, List, Tuple
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    """资讯分析器类"""
    
    def __init__(self, db_path: str, api_key: str = None):
        """
        初始化资讯分析器
        
        Args:
            db_path: SQLite数据库路径
            api_key: 大模型API密钥
        """
        self.db_path = db_path
        self.api_key = api_key
        if not api_key:
            self._load_api_key()
    
    def _load_api_key(self) -> None:
        """从数据库加载API密钥"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT api_key FROM api_config WHERE api_name = 'deepseek'")
            result = cursor.fetchone()
            
            if result:
                self.api_key = result[0]
            
            conn.close()
        except Exception as e:
            logger.error(f"加载API密钥失败: {str(e)}", exc_info=True)
    
    def get_unanalyzed_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取未分析的资讯
        
        Args:
            limit: 最大获取数量
            
        Returns:
            未分析的资讯列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, title, content, source, category, publish_date "
                "FROM news WHERE analyzed = 0 ORDER BY publish_date DESC LIMIT ?",
                (limit,)
            )
            
            news_list = [
                {
                    'id': row[0],
                    'title': row[1],
                    'content': row[2],
                    'source': row[3],
                    'category': row[4],
                    'publish_date': row[5]
                }
                for row in cursor.fetchall()
            ]
            
            conn.close()
            return news_list
        except Exception as e:
            logger.error(f"获取未分析资讯失败: {str(e)}", exc_info=True)
            return []
    
    def analyze_news(self, news_id: int, analysis_type: str = "一般摘要", 
                    max_length: int = 300) -> Optional[str]:
        """
        分析单条资讯
        
        Args:
            news_id: 资讯ID
            analysis_type: 分析类型，如"一般摘要"、"技术分析"等
            max_length: 摘要最大长度
            
        Returns:
            分析结果文本，失败时返回None
        """
        try:
            # 获取资讯内容
            news_data = self._get_news_by_id(news_id)
            if not news_data:
                logger.error(f"找不到ID为 {news_id} 的资讯")
                return None
            
            # 构造提示词
            prompt = self._build_prompt(news_data, analysis_type, max_length)
            
            # 调用大模型API
            summary = self._call_llm_api(prompt)
            
            if summary:
                # 保存分析结果
                self._save_analysis_result(news_id, summary)
                return summary
            else:
                return None
        except Exception as e:
            logger.error(f"分析资讯失败: {str(e)}", exc_info=True)
            return None
    
    def analyze_batch(self, analysis_type: str = "一般摘要", 
                     max_length: int = 300, batch_size: int = 5) -> int:
        """
        批量分析资讯
        
        Args:
            analysis_type: 分析类型
            max_length: 摘要最大长度
            batch_size: 批处理大小
            
        Returns:
            成功分析的资讯数量
        """
        news_list = self.get_unanalyzed_news(batch_size)
        
        success_count = 0
        for news in news_list:
            result = self.analyze_news(news['id'], analysis_type, max_length)
            if result:
                success_count += 1
        
        return success_count
    
    def _get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """
        通过ID获取资讯
        
        Args:
            news_id: 资讯ID
            
        Returns:
            资讯数据，失败时返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, title, content, source, category, publish_date "
                "FROM news WHERE id = ?",
                (news_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'content': row[2],
                    'source': row[3],
                    'category': row[4],
                    'publish_date': row[5]
                }
            else:
                return None
        except Exception as e:
            logger.error(f"获取资讯失败: {str(e)}", exc_info=True)
            return None
    
    def _build_prompt(self, news_data: Dict[str, Any], analysis_type: str, 
                     max_length: int) -> str:
        """
        构建大模型提示词
        
        Args:
            news_data: 资讯数据
            analysis_type: 分析类型
            max_length: 最大长度
            
        Returns:
            提示词文本
        """
        title = news_data['title']
        content = news_data['content']
        category = news_data['category']
        
        # 根据不同分析类型构建不同提示词
        if analysis_type == "技术分析":
            prompt = (
                f"请对以下技术资讯进行专业分析，重点提取技术细节、创新点和潜在影响，"
                f"最后总结该技术的未来发展趋势。摘要控制在{max_length}字以内。\n\n"
                f"标题: {title}\n\n"
                f"内容: {content}"
            )
        elif analysis_type == "趋势洞察":
            prompt = (
                f"请对以下{category}领域资讯进行深度趋势分析，识别行业发展模式，"
                f"预测未来发展方向，并说明可能带来的商业机会。摘要控制在{max_length}字以内。\n\n"
                f"标题: {title}\n\n"
                f"内容: {content}"
            )
        elif analysis_type == "竞争分析":
            prompt = (
                f"请从竞争情报角度分析以下资讯，重点关注市场参与者的战略动向、"
                f"竞争格局变化和市场份额影响。摘要控制在{max_length}字以内。\n\n"
                f"标题: {title}\n\n"
                f"内容: {content}"
            )
        elif analysis_type == "学术研究":
            prompt = (
                f"请以学术视角分析以下研究相关资讯，提取研究方法、关键发现、"
                f"创新点和学术价值，并指出研究局限性。摘要控制在{max_length}字以内。\n\n"
                f"标题: {title}\n\n"
                f"内容: {content}"
            )
        else:  # 默认为一般摘要
            prompt = (
                f"请对以下{category}领域资讯生成一份简洁明了的摘要，"
                f"提取核心事实、关键数据和主要观点。摘要控制在{max_length}字以内。\n\n"
                f"标题: {title}\n\n"
                f"内容: {content}"
            )
        
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
            '''
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are an expert analyst."},
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
            '''
            
            # 模拟返回结果
            mock_summary = f"这是一个模拟的分析结果。实际应用中将返回由大模型生成的内容分析和摘要。\n\n"
            mock_summary += "分析要点：\n1. 主要内容概述\n2. 关键数据和事实\n3. 行业影响分析\n4. 未来趋势预测"
            
            return mock_summary
        except Exception as e:
            logger.error(f"调用大模型API失败: {str(e)}", exc_info=True)
            return None
    
    def _save_analysis_result(self, news_id: int, summary: str) -> bool:
        """
        保存分析结果
        
        Args:
            news_id: 资讯ID
            summary: 分析结果文本
            
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 更新资讯记录
            cursor.execute(
                "UPDATE news SET summary = ?, analyzed = 1 WHERE id = ?",
                (summary, news_id)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"成功保存资讯ID {news_id} 的分析结果")
            return True
        except Exception as e:
            logger.error(f"保存分析结果失败: {str(e)}", exc_info=True)
            return False 