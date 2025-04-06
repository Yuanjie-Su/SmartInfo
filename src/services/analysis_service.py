#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Intelligent Analysis Service Module
Responsible for calling the large model API to analyze and generate summaries of news content
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

from src.db.repositories import NewsRepository
from .llm_client import LLMClient  # Use the consolidated client

logger = logging.getLogger(__name__)

DEFAULT_ANALYSIS_MODEL = "deepseek-chat"  # Or make this configurable


class AnalysisService:
    """News Analysis Service Class"""

    def __init__(self, news_repo: NewsRepository, llm_client: LLMClient):
        self._news_repo = news_repo
        self._llm_client = llm_client

    def get_unanalyzed_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get unanalyzed news (for display in the analysis tab or background processing)
        """
        return self._news_repo.get_unanalyzed(limit)

    async def analyze_single_news(
        self, news_id: int, analysis_type: str = "General Summary", max_length: int = 300
    ) -> Optional[str]:
        """
        Asynchronously analyze a single news item and save the result

        Args:
            news_id: News ID
            analysis_type: Type of analysis (used to build the prompt)
            max_length: Expected maximum length of the summary (prompt for LLM)

        Returns:
            Analysis result text, returns None on failure
        """
        try:
            # Get news content (only the part needed for analysis)
            # Use get_unanalyzed fields which include content/summary
            news_data = self._news_repo.get_by_id(
                news_id
            )  # Need full data including summary/content
            if not news_data:
                logger.error(f"Could not find news with ID {news_id} for analysis.")
                return None
            if news_data["analyzed"]:
                logger.warning(
                    f"News ID {news_id} is already analyzed. Returning existing analysis."
                )
                return news_data.get("llm_analysis")

            # Select text to analyze (prefer content, fallback to summary)
            text_to_analyze = news_data.get("content") or news_data.get("summary") or ""
            if not text_to_analyze:
                logger.warning(
                    f"No content or summary found for news ID {news_id}. Cannot analyze."
                )
                # Mark as analyzed to avoid retrying? Or leave as unanalyzed? Let's mark it.
                self._news_repo.update_analysis(news_id, "Cannot analyze: missing content or summary")
                return "Cannot analyze: missing content or summary"

            # Construct the prompt
            prompt = self._build_analysis_prompt(
                news_data["title"],
                text_to_analyze,
                news_data["category_name"],
                analysis_type,
                max_length,
            )

            # Call the large model API (using asynchronous method)
            logger.info(
                f"Requesting analysis for news ID {news_id} (type: {analysis_type})"
            )
            analysis_result = await self._llm_client.get_completion_content(
                model=DEFAULT_ANALYSIS_MODEL,
                messages=[
                    # Optional System Prompt for context
                    {
                        "role": "system",
                        "content": "You are an expert news analyst. Provide concise and insightful analysis based on the given text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_length
                + 200,  # Allow some buffer for the LLM's own structure/wording
                temperature=0.5,  # Slightly more creative for analysis/summary
            )

            if analysis_result:
                logger.info(f"Successfully received analysis for news ID {news_id}")
                # Save analysis result (Repository handles marking as analyzed)
                if self._news_repo.update_analysis(news_id, analysis_result):
                    return analysis_result
                else:
                    logger.error(
                        f"Failed to save analysis result for news ID {news_id} to DB."
                    )
                    # Return result anyway, but log the DB error
                    return analysis_result
            else:
                logger.error(f"LLM analysis failed for news ID {news_id}.")
                # Optionally mark as failed analysis in DB?
                self._news_repo.update_analysis(news_id, "Analysis failed: LLM did not return result")
                return None
        except Exception as e:
            logger.error(f"Error analyzing news ID {news_id}: {e}", exc_info=True)
            try:
                # Attempt to mark as failed in DB
                self._news_repo.update_analysis(
                    news_id, f"Analysis failed: internal error ({type(e).__name__})"
                )
            except Exception as db_err:
                logger.error(
                    f"Failed to mark news ID {news_id} as failed analysis in DB: {db_err}"
                )
            return None

    async def analyze_batch(
        self,
        batch_size: int = 5,
        analysis_type: str = "General Summary",
        max_length: int = 300,
    ) -> int:
        """
        Batch analyze unanalyzed news (for background tasks)

        Returns:
            Number of successfully analyzed news items
        """
        unanalyzed_news = self.get_unanalyzed_news(batch_size)
        if not unanalyzed_news:
            logger.info("No unanalyzed news found for batch processing.")
            return 0

        logger.info(f"Starting batch analysis for {len(unanalyzed_news)} news items...")

        tasks = [
            self.analyze_single_news(news["id"], analysis_type, max_length)
            for news in unanalyzed_news
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for i, result in enumerate(results):
            news_id = unanalyzed_news[i]["id"]
            if isinstance(
                result, str
            ):  # Successfully analyzed and saved (or marked failed)
                success_count += 1
                logger.info(f"Batch analysis completed for news ID {news_id}.")
            elif isinstance(result, Exception):
                logger.error(
                    f"Error during batch analysis for news ID {news_id}: {result}",
                    exc_info=result,
                )
            elif result is None:
                logger.error(
                    f"Batch analysis returned None (likely LLM failure) for news ID {news_id}."
                )
                # The analyze_single_news function should have tried to mark it failed in DB
            else:
                logger.warning(
                    f"Unexpected result type {type(result)} for news ID {news_id} in batch analysis."
                )

        logger.info(
            f"Batch analysis finished. Successfully processed (analyzed or marked failed): {success_count}/{len(unanalyzed_news)}"
        )
        return success_count

    def _build_analysis_prompt(
        self,
        title: str,
        text: str,
        category: Optional[str],
        analysis_type: str,
        max_length: int,
    ) -> str:
        """Construct the prompt for large model analysis"""

        category_info = f" in the {category} category" if category else ""

        # Base instruction
        prompt = f"Please perform a '{analysis_type}' analysis on the following news article{category_info}. Limit your response to approximately {max_length} characters.\n\n"
        prompt += f"Title: {title}\n\n"
        prompt += f"Content:\n---\n{text}\n---\n\n"

        # Specific instructions based on type
        if analysis_type == "Technical Analysis":
            prompt += "Focus on: technical details, innovations, potential impact, and future development trends."
        elif analysis_type == "Trend Insights":
            prompt += "Focus on: identifying industry patterns, predicting future directions, and potential business opportunities."
        elif analysis_type == "Competitive Analysis":
            prompt += "Focus on: strategic moves of market players, changes in competitive landscape, and market share implications."
        elif analysis_type == "Academic Research":
            prompt += "Focus on: research methodology, key findings, novelty, academic value, and limitations of the research."
        else:  # Default: General Summary
            prompt += "Focus on: summarizing the core facts, key data points, and main conclusions concisely."

        prompt += "\n\nAnalysis:"
        return prompt
