# -*- coding: utf-8 -*-

"""
LLM Client module
Responsible for interacting with Large Language Models (LLMs)
"""

import asyncio
from datetime import datetime
import logging
import os
import io
import ijson
import time
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Generator,
    Iterator,
    List,
    Dict,
    Any,
    Optional,
    Union,
)

from openai import APIError, AsyncOpenAI, OpenAI, ChatCompletion

logger = logging.getLogger(__name__)


class LLMClient:
    """
    A client for interacting with Large Language Models (LLMs),
    supporting both synchronous and asynchronous operations using the OpenAI library interface.
    Compatible with OpenAI, DeepSeek, and other OpenAI-compatible APIs.
    """

    def __init__(
        self, base_url: str, api_key: Optional[str], async_mode: bool = False
    ) -> None:
        """
        Initializes the LLM Client.

        Args:
            base_url: The base URL of the LLM API (e.g., "https://api.deepseek.com").
            api_key: The API key for authentication. Can be None if authentication is handled differently (e.g., Azure).
            async_mode: Whether to operate in asynchronous mode.
        """
        if not api_key:
            # Allow for scenarios like Azure AD auth where key might be optional/handled by library
            logger.warning(
                f"Initializing LLMClient for {base_url} without an explicit API key."
            )
        self.base_url = base_url
        self.api_key = api_key
        self.async_mode = async_mode
        self._client = None

    def __enter__(self):
        """Context manager entry point for synchronous usage."""
        if self.async_mode:
            raise RuntimeError(
                "Cannot use synchronous context manager with async_mode=True"
            )
        self._client = self._create_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point for synchronous usage."""
        if hasattr(self._client, "close"):
            self._client.close()
        self._client = None

    async def __aenter__(self):
        """Context manager entry point for asynchronous usage."""
        if not self.async_mode:
            raise RuntimeError(
                "Cannot use asynchronous context manager with async_mode=False"
            )
        self._client = self._create_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point for asynchronous usage."""
        if hasattr(self._client, "close"):
            await self._client.close()
        self._client = None

    def _create_client(self) -> Union[OpenAI, AsyncOpenAI]:
        """Creates the appropriate OpenAI client (sync or async)."""
        common_args = {
            "base_url": self.base_url,
            "api_key": self.api_key,
        }
        if self.async_mode:
            logger.debug(f"Creating AsyncOpenAI client for {self.base_url}")
            return AsyncOpenAI(**common_args)
        else:
            logger.debug(f"Creating OpenAI client for {self.base_url}")
            return OpenAI(**common_args)

    def _ensure_client(self):
        """Ensures client is initialized if not using context manager."""
        if self._client is None:
            self._client = self._create_client()
            logger.debug("Auto-initializing LLM client outside of context manager")

    async def get_completion_content(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 1500,
        temperature: float = 0.3,
        max_retries: int = 3,
        **kwargs,  # Allow passing other API params like top_p, presence_penalty etc.
    ) -> Optional[str]:
        """
        Retrieves the completion content from the LLM (non-streaming).

        Args:
            model: The name of the LLM model to use (e.g., "deepseek-chat").
            messages: The list of messages to send to the LLM.
            max_tokens: The maximum number of tokens to generate.
            temperature: Sampling temperature.
            max_retries: The number of times to retry the API call on failure.
            **kwargs: Additional parameters for the API call.

        Returns:
            The generated text content, or None on failure after retries.
        """
        self._ensure_client()

        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        logger.debug(f"LLM non-streaming request: {request_params}")

        for attempt in range(max_retries):
            try:
                if self.async_mode:
                    if not isinstance(self._client, AsyncOpenAI):
                        raise TypeError("Client is not in async mode.")
                    completion = await self._client.chat.completions.create(
                        **request_params
                    )
                else:
                    if not isinstance(self._client, OpenAI):
                        raise TypeError("Client is not in sync mode.")
                    completion = self._client.chat.completions.create(**request_params)

                # Log usage information if available
                if completion.usage:
                    logger.info(
                        f"LLM API Usage: Prompt={completion.usage.prompt_tokens}, Completion={completion.usage.completion_tokens}, Total={completion.usage.total_tokens}"
                    )

                if (
                    completion.choices
                    and completion.choices[0].message
                    and completion.choices[0].message.content
                ):
                    logger.debug("LLM non-streaming response received successfully.")
                    return completion.choices[0].message.content
                else:
                    logger.warning(
                        f"LLM API call successful but no content in response (Attempt {attempt + 1}/{max_retries}). Finish reason: {completion.choices[0].finish_reason if completion.choices else 'N/A'}"
                    )
                    # Don't retry if the finish reason indicates a content filter or length issue
                    if completion.choices and completion.choices[
                        0
                    ].finish_reason not in [None, "stop"]:
                        break  # Exit retry loop for specific non-retryable finish reasons

            except APIError as e:
                logger.error(
                    f"LLM API Error (Attempt {attempt + 1}/{max_retries}) for model {model}: {e}",
                    exc_info=True,
                )
                # Implement backoff strategy
                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                (
                    await asyncio.sleep(wait_time)
                    if self.async_mode
                    else time.sleep(wait_time)
                )
            except Exception as e:
                logger.error(
                    f"Unexpected Error during LLM call (Attempt {attempt + 1}/{max_retries}) for model {model}: {e}",
                    exc_info=True,
                )
                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                (
                    await asyncio.sleep(wait_time)
                    if self.async_mode
                    else time.sleep(wait_time)
                )

        logger.error(
            f"Failed to get LLM completion for model {model} after {max_retries} attempts."
        )
        return None

    async def stream_completion_content(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 1500,
        temperature: float = 0.3,
        **kwargs,  # Allow passing other API params
    ) -> Union[AsyncGenerator[str, None], Generator[str, None, None], None]:
        """
        Retrieves the completion content from the LLM in streaming mode.

        Yields text chunks. Returns None if the initial API call fails.
        Handles potential errors during stream iteration internally.

        Args:
            model: The name of the LLM model.
            messages: The list of messages.
            max_tokens: The maximum number of tokens to generate.
            temperature: Sampling temperature.
            **kwargs: Additional parameters for the API call.


        Returns:
            An async generator (async mode) or a regular generator (sync mode)
            yielding text chunks, or None if the stream could not be initiated.
        """
        self._ensure_client()

        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        logger.debug(f"LLM streaming request: {request_params}")

        try:
            if self.async_mode:
                if not isinstance(self._client, AsyncOpenAI):
                    raise TypeError("Client is not in async mode.")
                stream = await self._client.chat.completions.create(**request_params)
                logger.debug("Async LLM stream initiated.")
                return self._async_stream_processor(
                    stream, model
                )  # Return the generator immediately
            else:
                if not isinstance(self._client, OpenAI):
                    raise TypeError("Client is not in sync mode.")
                stream = self._client.chat.completions.create(**request_params)
                logger.debug("Sync LLM stream initiated.")
                return self._sync_stream_processor(
                    stream, model
                )  # Return the generator immediately

        except APIError as e:
            logger.error(
                f"LLM API Error initiating stream for model {model}: {e}", exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected Error initiating stream for model {model}: {e}",
                exc_info=True,
            )
            return None

    async def _async_stream_processor(
        self, stream: AsyncIterator, model_name: str
    ) -> AsyncGenerator[str, None]:
        """Helper to process async stream chunks and handle errors."""
        total_chunks = 0
        try:
            async for chunk in stream:
                total_chunks += 1
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason
                    if delta and delta.content:
                        yield delta.content
                    if finish_reason:
                        logger.info(
                            f"LLM stream finished for model {model_name}. Reason: {finish_reason}. Total chunks: {total_chunks}"
                        )
                        # Log usage if available on the *last* chunk (some APIs provide it here)
                        if hasattr(chunk, "usage") and chunk.usage:
                            logger.info(
                                f"LLM API Usage (final chunk): Prompt={chunk.usage.prompt_tokens}, Completion={chunk.usage.completion_tokens}, Total={chunk.usage.total_tokens}"
                            )
                        break  # End the generator
        except APIError as e:
            logger.error(
                f"LLM API Error during async stream processing for model {model_name}: {e}",
                exc_info=True,
            )
            # Yielding an error or logging might be appropriate depending on use case
            # yield f"STREAM_ERROR: {e}"
        except Exception as e:
            logger.error(
                f"Unexpected error during async stream processing for model {model_name}: {e}",
                exc_info=True,
            )
            # yield f"STREAM_ERROR: Unexpected error"
        finally:
            logger.debug(
                f"Async stream processing ended for model {model_name}. Total chunks processed: {total_chunks}"
            )

    def _sync_stream_processor(
        self, stream: Iterator, model_name: str
    ) -> Generator[str, None, None]:
        """Helper to process sync stream chunks and handle errors."""
        total_chunks = 0
        try:
            for chunk in stream:
                total_chunks += 1
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason
                    if delta and delta.content:
                        yield delta.content
                    if finish_reason:
                        logger.info(
                            f"LLM stream finished for model {model_name}. Reason: {finish_reason}. Total chunks: {total_chunks}"
                        )
                        if hasattr(chunk, "usage") and chunk.usage:
                            logger.info(
                                f"LLM API Usage (final chunk): Prompt={chunk.usage.prompt_tokens}, Completion={chunk.usage.completion_tokens}, Total={chunk.usage.total_tokens}"
                            )
                        break
        except APIError as e:
            logger.error(
                f"LLM API Error during sync stream processing for model {model_name}: {e}",
                exc_info=True,
            )
            # yield f"STREAM_ERROR: {e}"
        except Exception as e:
            logger.error(
                f"Unexpected error during sync stream processing for model {model_name}: {e}",
                exc_info=True,
            )
            # yield f"STREAM_ERROR: Unexpected error"
        finally:
            logger.debug(
                f"Sync stream processing ended for model {model_name}. Total chunks processed: {total_chunks}"
            )
