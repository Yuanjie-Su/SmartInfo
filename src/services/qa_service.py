#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Question and Answer Service Module
Implements simple Q&A functions by directly querying the LLM.
"""

import logging
from typing import List, Dict, Any, Optional

from src.db.repositories import QARepository
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_QA_MODEL = "deepseek-chat"


class QAService:
    """Question and Answer Service Class"""

    def __init__(
        self,
        qa_repo: QARepository,
        llm_client: LLMClient,
    ):
        self._qa_repo = qa_repo
        self._llm_client = llm_client

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
        if not self._llm_client:
            return {
                "answer": "Q&A service is not fully initialized, please try again later.",
                "error": "Service not ready",
            }

        if not question or not question.strip():
            return {
                "answer": "Please enter a valid question.",
                "error": "Empty question",
            }

        try:
            logger.info(f"Answering question directly via LLM: '{question}'")

            # 1. Prepare simple prompt for LLM
            # No context retrieval needed anymore
            prompt = self._build_direct_qa_prompt(question)

            # 2. Call LLM
            logger.debug("Sending direct query to LLM...")
            llm_response = await self._llm_client.generate_response(
                prompt=prompt,
                model=DEFAULT_QA_MODEL,
                max_tokens=1024, # Adjust as needed
                temperature=0.7,
            )

            # 3. Process response
            if llm_response and llm_response.get("status") == "success":
                answer = llm_response.get("content", "Could not generate an answer.").strip()
                logger.info(f"LLM Answer received: '{answer[:100]}...'")

                # Save Q&A pair to history (without sources)
                try:
                    self._qa_repo.add_qa(question, answer, "[]") # Store empty list as JSON for sources
                except Exception as db_err:
                    logger.error(f"Failed to save Q&A to history: {db_err}", exc_info=True)

                return {"answer": answer}
            else:
                error_msg = llm_response.get("error", "Unknown LLM error")
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
