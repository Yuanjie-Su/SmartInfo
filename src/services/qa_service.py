#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Question and Answer Service Module
Implements semantic retrieval and Q&A functions based on the knowledge base
"""

import logging
import chromadb
from sentence_transformers import SentenceTransformer, util
from typing import List, Dict, Any, Optional

from src.db.repositories import NewsRepository, QARepository
from .llm_client import LLMClient
from src.config import AppConfig, CONFIG_KEY_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

DEFAULT_QA_MODEL = "deepseek-chat"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RELEVANCE_THRESHOLD = 0.4  # Cosine similarity threshold (higher is better)


class QAService:
    """Question and Answer Service Class"""

    def __init__(
        self,
        config: AppConfig,
        news_repo: NewsRepository,
        qa_repo: QARepository,
        chroma_client: chromadb.Client,
        llm_client: LLMClient,
    ):
        self._config = config
        self._news_repo = news_repo
        self._qa_repo = qa_repo
        self._chroma_client = chroma_client
        self._llm_client = llm_client
        self._embedding_model_name = self._config.get_persistent(
            CONFIG_KEY_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL
        )
        self._embedding_model = self._load_embedding_model()
        self._chroma_collection = self._get_chroma_collection()

    def _load_embedding_model(self) -> SentenceTransformer:
        """Load embedding model"""
        model_name = self._embedding_model_name
        logger.info(f"Loading embedding model: {model_name}")
        try:
            return SentenceTransformer(model_name)
        except Exception as e:
            logger.error(
                f"Failed to load primary embedding model '{model_name}': {e}",
                exc_info=True,
            )
            # Fallback logic
            if model_name != DEFAULT_EMBEDDING_MODEL:
                logger.warning(
                    f"Attempting to load fallback default model: {DEFAULT_EMBEDDING_MODEL}"
                )
                try:
                    self._embedding_model_name = (
                        DEFAULT_EMBEDDING_MODEL  # Update internal name
                    )
                    return SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
                except Exception as e2:
                    logger.critical(
                        f"Failed to load fallback embedding model '{DEFAULT_EMBEDDING_MODEL}': {e2}",
                        exc_info=True,
                    )
                    raise RuntimeError("Could not load any embedding model.") from e2
            else:
                # Already tried default, critical failure
                raise RuntimeError(
                    f"Could not load default embedding model '{DEFAULT_EMBEDDING_MODEL}'."
                ) from e

    def _get_chroma_collection(self) -> Optional[chromadb.Collection]:
        """Get or create ChromaDB collection"""
        try:
            # Ensure collection exists
            collection = self._chroma_client.get_or_create_collection("news_collection")
            logger.info("ChromaDB collection 'news_collection' accessed successfully.")
            return collection
        except Exception as e:
            logger.error(
                f"Failed to get or create ChromaDB collection 'news_collection': {e}",
                exc_info=True,
            )
            return None  # Service might be degraded

    # --- Embedding Management ---

    def update_embeddings_for_unanalyzed(self, batch_size: int = 50) -> int:
        """
        Create and store embeddings for news that have not been embedded.

        Returns:
            The number of records successfully created and stored embeddings.
        """
        if not self._embedding_model or not self._chroma_collection:
            logger.error(
                "Cannot update embeddings: Embedding model or ChromaDB collection not available."
            )
            return 0

        items_to_embed = self._news_repo.get_unembedded(batch_size)
        if not items_to_embed:
            logger.info("No new items found needing embedding.")
            return 0

        logger.info(f"Found {len(items_to_embed)} items to embed.")

        texts_to_encode = []
        ids_to_encode = []
        metadatas_to_encode = []
        db_ids_to_mark = []

        for item in items_to_embed:
            # Combine title, summary, and content for embedding
            # Prioritize content if available
            content = item.get("content") or item.get("summary") or ""
            title = item.get("title", "")
            full_text = f"Title: {title}\n\n{content}".strip()

            if not full_text:
                logger.warning(
                    f"Skipping embedding for news ID {item['id']} due to empty content."
                )
                # Mark as embedded to avoid retrying? Or leave unembedded? Let's skip marking for now.
                continue

            texts_to_encode.append(full_text)
            chroma_id = f"news_{item['id']}"  # ChromaDB ID format
            ids_to_encode.append(chroma_id)
            metadatas_to_encode.append(
                {
                    "db_id": str(item["id"]),  # Store original DB ID in metadata
                    "title": title,
                    # Add other relevant metadata? Source? Category? Date?
                }
            )
            db_ids_to_mark.append(item["id"])  # DB IDs to update status later

        if not texts_to_encode:
            logger.info("No valid texts found to encode after filtering.")
            return 0

        # Generate embeddings in batch
        try:
            logger.info(f"Generating embeddings for {len(texts_to_encode)} items...")
            embeddings = self._embedding_model.encode(
                texts_to_encode, show_progress_bar=False
            ).tolist()
            logger.info("Embeddings generated.")
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}", exc_info=True)
            return 0

        # Upsert into ChromaDB
        try:
            logger.info(f"Upserting {len(ids_to_encode)} embeddings into ChromaDB...")
            self._chroma_collection.upsert(
                ids=ids_to_encode,
                embeddings=embeddings,
                documents=texts_to_encode,  # Store the text used for embedding
                metadatas=metadatas_to_encode,
            )
            logger.info("Embeddings upserted into ChromaDB.")

            # Mark items as embedded in SQLite DB
            if self._news_repo.mark_embedded_batch(db_ids_to_mark):
                logger.info(
                    f"Marked {len(db_ids_to_mark)} items as embedded in SQLite."
                )
                return len(db_ids_to_mark)
            else:
                logger.error(
                    "Failed to mark all items as embedded in SQLite after ChromaDB upsert."
                )
                # Data inconsistency - needs attention
                return 0  # Report 0 success as the process didn't fully complete

        except Exception as e:
            logger.error(
                f"Failed to upsert embeddings to ChromaDB or mark in SQLite: {e}",
                exc_info=True,
            )
            return 0

    def clear_all_embeddings(self) -> bool:
        """Clears all embeddings from ChromaDB and resets flags in SQLite."""
        if not self._chroma_collection:
            logger.error("ChromaDB collection not available, cannot clear embeddings.")
            return False
        try:
            logger.warning(
                "Clearing all embeddings from ChromaDB collection 'news_collection'."
            )
            # Get all IDs currently in the collection
            existing_ids = self._chroma_collection.get(include=[])["ids"]
            if existing_ids:
                self._chroma_collection.delete(ids=existing_ids)
                logger.info(f"Deleted {len(existing_ids)} embeddings from ChromaDB.")
            else:
                logger.info("ChromaDB collection was already empty.")

            # Reset embedded flag in SQLite (might be slow on large tables without index)
            # Consider doing this in batches if needed
            logger.warning("Resetting 'embedded' flag for all news items in SQLite.")
            cursor = self._news_repo._execute(
                "UPDATE news SET embedded = 0", commit=True
            )  # Use base execute
            if cursor:
                logger.info("Reset 'embedded' flag in SQLite.")
                return True
            else:
                logger.error("Failed to reset 'embedded' flag in SQLite.")
                return False
        except Exception as e:
            logger.error(f"Error clearing embeddings: {e}", exc_info=True)
            return False

    # --- Question Answering ---

    async def answer_question(
        self, question: str, num_results: int = 5
    ) -> Dict[str, Any]:
        """
        Answers a user's question based on semantic search of the news knowledge base.

        Args:
            question: The user's question.
            num_results: The number of relevant documents to retrieve.

        Returns:
            A dictionary containing the 'answer' and 'sources' (relevant news items).
            Includes an 'error' key if something went wrong.
        """
        if (
            not self._embedding_model
            or not self._chroma_collection
            or not self._llm_client
        ):
            return {
                "answer": "The Q&A service is not fully initialized, please try again later.",
                "sources": [],
                "error": "Service not ready",
            }

        if not question or not question.strip():
            return {
                "answer": "Please enter a valid question.",
                "sources": [],
                "error": "Empty question",
            }

        try:
            logger.info(f"Answering question: '{question}'")
            # 1. Generate embedding for the question
            question_embedding = self._embedding_model.encode(question).tolist()

            # 2. Query ChromaDB for relevant documents
            logger.debug(f"Querying ChromaDB for {num_results} results...")
            results = self._chroma_collection.query(
                query_embeddings=[question_embedding],
                n_results=num_results,
                include=["documents", "metadatas", "distances"],  # Cosine distance
            )
            logger.debug(f"ChromaDB query results: {results}")

            # 3. Filter and format relevant contexts/sources
            contexts = []
            sources_info = []
            if results and results.get("ids") and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    distance = results["distances"][0][i]
                    # Convert cosine distance to similarity (0 to 1, higher is better)
                    similarity = 1 - distance  # Assuming distance is cosine distance
                    metadata = results["metadatas"][0][i]
                    doc_content = results["documents"][0][i]  # Text used for embedding

                    if similarity >= DEFAULT_RELEVANCE_THRESHOLD:
                        db_id_str = metadata.get("db_id")
                        db_id = (
                            int(db_id_str)
                            if db_id_str and db_id_str.isdigit()
                            else None
                        )

                        contexts.append(doc_content)  # Use the embedded text as context
                        sources_info.append(
                            {
                                "id": db_id,  # Actual DB ID
                                "title": metadata.get("title", "Unknown Title"),
                                "preview": (
                                    doc_content[:250] + "..."
                                    if len(doc_content) > 250
                                    else doc_content
                                ),  # Preview from embedded text
                                "similarity": round(similarity * 100),  # Percentage
                            }
                        )
                    else:
                        logger.debug(
                            f"Skipping result due to low similarity ({similarity:.2f} < {DEFAULT_RELEVANCE_THRESHOLD}): {metadata.get('title')}"
                        )

            if not contexts:
                logger.info(
                    "No relevant documents found in knowledge base for the question."
                )
                return {
                    "answer": "Sorry, I couldn't find any information related to your question in the knowledge base.",
                    "sources": [],
                    "error": None,
                }

            logger.info(f"Found {len(contexts)} relevant documents.")

            # 4. Build prompt for LLM
            prompt = self._build_qa_prompt(question, contexts)

            # 5. Call LLM for answer generation
            logger.info("Generating answer using LLM...")
            answer = await self._llm_client.get_completion_content(
                model=DEFAULT_QA_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant answering questions based *only* on the provided context. If the context doesn't contain the answer, say you don't know.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,  # More factual
                max_tokens=1000,  # Allow longer answers
            )

            if not answer:
                logger.error("LLM failed to generate an answer.")
                return {
                    "answer": "Sorry, there was a problem generating the answer.",
                    "sources": sources_info,
                    "error": "LLM generation failed",
                }

            logger.info("LLM answer generated successfully.")

            # 6. Save Q&A history (optional, can be done async)
            context_db_ids = [
                str(s["id"]) for s in sources_info if s.get("id") is not None
            ]
            self._qa_repo.add_entry(question, answer, context_db_ids)

            return {"answer": answer, "sources": sources_info, "error": None}

        except Exception as e:
            logger.error(f"Error during question answering: {e}", exc_info=True)
            return {
                "answer": "An error occurred while processing your question.",
                "sources": [],
                "error": str(e),
            }

    def _build_qa_prompt(self, question: str, contexts: List[str]) -> str:
        """Builds the prompt for the LLM based on the question and retrieved contexts."""
        context_section = "\n\n".join(
            f"Context {i+1}:\n{ctx}" for i, ctx in enumerate(contexts)
        )

        prompt = f"""Based *only* on the following context, please answer the user's question. Do not use any prior knowledge. If the answer is not found in the context, state that clearly.

Contexts:
---
{context_section}
---

User Question: {question}

Answer:"""
        return prompt

    # --- History Management ---

    def get_qa_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves the recent Q&A history."""
        return self._qa_repo.get_history(limit)

    def clear_qa_history(self) -> bool:
        """Clears the Q&A history."""
        return self._qa_repo.clear_history()
