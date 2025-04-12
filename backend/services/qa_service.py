# backend/services/qa_service.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Question and Answer Service Module
Implements simple Q&A functions by directly querying the LLM.
"""

import logging
import json
from typing import List, Dict, Any, Optional, AsyncGenerator

from backend.db.repositories import QARepository
from backend.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Use a model appropriate for direct Q&A
DEFAULT_QA_MODEL = "deepseek-chat" # Or another suitable model

class QAService:
    """Question and Answer Service Class"""

    def __init__(
        self,
        qa_repo: QARepository,
        llm_client: LLMClient, # Expecting the general client
    ):
        self._qa_repo = qa_repo
        # Use a specific LLM client instance if needed, or configure the main one
        # For simplicity, assume the passed llm_client is suitable or can be configured
        self._llm_client = llm_client
        if not self._llm_client:
            logger.error("QAService initialized without a valid LLMClient!")


    async def answer_question_non_streaming(
        self, question: str
    ) -> Dict[str, Any]:
        """
        Answers a user's question by directly querying the LLM (non-streaming).

        Args:
            question: The user's question.

        Returns:
            A dictionary containing the 'answer' or 'error'.
        """
        if not self._llm_client:
            logger.error("LLMClient not available for QAService.")
            return {"answer": None, "error": "QA Service LLM client not configured."}

        if not question or not question.strip():
            return {"answer": None, "error": "Question cannot be empty."}

        try:
            logger.info(f"Answering question non-streaming: '{question}'")

            # 1. Prepare simple prompt for LLM
            messages = self._build_direct_qa_messages(question)

            # 2. Call LLM using get_completion_content (non-streaming)
            logger.debug("Sending direct non-streaming query to LLM...")
            answer_content = await self._llm_client.get_completion_content(
                model=DEFAULT_QA_MODEL,
                messages=messages,
                max_tokens=1024, # Adjust as needed
                temperature=0.7,
            )

            # 3. Process response
            if answer_content:
                answer = answer_content.strip()
                logger.info(f"LLM non-streaming answer received: '{answer[:100]}...'")

                # Save Q&A pair to history
                self._try_save_qa(question, answer)

                return {"answer": answer, "error": None}
            else:
                error_msg = "LLM did not return an answer."
                logger.error(f"LLM non-streaming query failed: {error_msg}")
                return {"answer": None, "error": error_msg}

        except Exception as e:
            logger.error(f"Error during non-streaming question answering: {e}", exc_info=True)
            return {"answer": None, "error": f"An unexpected error occurred: {str(e)}"}


    async def answer_question_streaming(
        self, question: str
    ) -> Optional[AsyncGenerator[str, None]]:
        """
        Answers a user's question by directly querying the LLM (streaming).

        Args:
            question: The user's question.

        Returns:
            An async generator yielding answer chunks, or None if setup fails.
        """
        if not self._llm_client or not self._llm_client.async_mode:
             logger.error("Async LLMClient not available or not in async mode for QA streaming.")
             # Cannot stream synchronously, return None or raise error
             return None # Indicate failure to start streaming

        if not question or not question.strip():
            logger.warning("Empty question received for streaming.")
            # Could yield an error message or return None
            async def empty_gen():
                yield "[Error: Question cannot be empty]"
                if False: # Make it a generator
                    yield
            return empty_gen() # Return an empty generator

        try:
            logger.info(f"Answering question streaming: '{question}'")
            messages = self._build_direct_qa_messages(question)

            stream_generator = await self._llm_client.stream_completion_content(
                model=DEFAULT_QA_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.7,
            )

            if stream_generator is None:
                logger.error("Failed to initiate LLM stream for QA.")
                async def error_gen():
                    yield "[Error: Failed to start LLM stream]"
                    if False: yield
                return error_gen()

            # We need to wrap the generator to save the full answer at the end
            return self._process_and_save_stream(question, stream_generator)

        except Exception as e:
            logger.error(f"Error setting up QA stream: {e}", exc_info=True)
            async def error_gen():
                 yield f"[Error: {str(e)}]"
                 if False: yield
            return error_gen()


    async def _process_and_save_stream(self, question: str, stream: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """Wraps the LLM stream generator to capture the full answer and save it."""
        full_answer_parts = []
        try:
            async for chunk in stream:
                full_answer_parts.append(chunk)
                yield chunk # Yield chunk to the caller immediately
        except Exception as e:
            logger.error(f"Error during QA stream processing: {e}", exc_info=True)
            yield f"[Stream Error: {str(e)}]" # Optionally yield error
            # Decide if partial answer should be saved on error? Probably not.
            return # Stop generation

        # Stream finished successfully, combine and save
        full_answer = "".join(full_answer_parts).strip()
        if full_answer:
            logger.info(f"Full streamed answer received: '{full_answer[:100]}...'")
            self._try_save_qa(question, full_answer)
        else:
            logger.warning("Stream completed but resulted in an empty answer.")


    def _try_save_qa(self, question: str, answer: str):
        """Attempts to save the Q&A pair to the database, logs errors."""
        try:
            # context_ids are not used in this simple direct QA, save as empty JSON list
            self._qa_repo.add_qa(question, answer, "[]")
        except Exception as db_err:
            # Log error but don't let DB error fail the primary QA function
            logger.error(f"Failed to save Q&A to history: {db_err}", exc_info=True)


    def _build_direct_qa_messages(self, question: str) -> List[Dict[str, str]]:
        """Builds a simple message list for the LLM."""
        # Can add system prompts or more complex structuring later if needed
        return [
            {"role": "user", "content": question}
        ]

    async def get_qa_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves Q&A history from the database."""
        try:
            return self._qa_repo.get_all_qa(limit, offset)
        except Exception as e:
            logger.error(f"Error fetching QA history: {e}", exc_info=True)
            return []

    async def get_qa_history_item(self, qa_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a specific QA history item by ID."""
        try:
            # QARepository doesn't have get_by_id, add it or implement here
            # Quick implementation using existing methods (less efficient)
            history = await self.get_qa_history(limit=10000, offset=0) # Adjust limit as needed
            for item in history:
                if item.get('id') == qa_id:
                    return item
            return None
            # Or add to QARepository:
            # return self._qa_repo.get_by_id(qa_id)
        except Exception as e:
             logger.error(f"Error fetching QA history item {qa_id}: {e}", exc_info=True)
             return None

    async def clear_qa_history(self) -> bool:
        """Clears all Q&A history."""
        logger.warning("Clearing all Q&A history.")
        try:
            return self._qa_repo.clear_history()
        except Exception as e:
            logger.error(f"Error clearing QA history: {e}", exc_info=True)
            return False

    async def delete_qa_entry(self, qa_id: int) -> bool:
        """Deletes a specific Q&A entry by its ID."""
        try:
            return self._qa_repo.delete_qa(qa_id)
        except Exception as e:
            logger.error(f"Error deleting QA entry {qa_id}: {e}", exc_info=True)
            return False