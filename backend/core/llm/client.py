# backend/core/llm/client.py
# -*- coding: utf-8 -*-

"""
LLM Client module
Responsible for interacting with Large Language Models (LLMs) via APIs
compatible with the OpenAI interface (e.g., OpenAI, DeepSeek, VolcEngine).
"""

import abc
import asyncio
import logging
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
    TypeVar,
    Generic,
    Type,
    cast,
)

# Use the official OpenAI library for interactions
from openai import (
    APIError,
    AsyncOpenAI,
    OpenAI,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Generic type for return values


class LLMClientBase(abc.ABC):
    """
    Abstract base class for LLM clients.

    Defines the interface that both sync and async clients must implement
    and provides common functionality.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str],
        model: Optional[str] = None,
        context_window: int = 4096,
        max_output_tokens: int = 2048,
        timeout: int = 600,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the LLM Client base.

        Args:
            base_url: The base URL of the LLM API.
            api_key: The API key for authentication. Can be None if auth is handled differently.
            model: Default model name to use if not specified in methods.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for transient API errors.
        """
        if not api_key:
            logger.warning(
                f"Initializing LLMClient for {base_url} without an explicit API key."
            )
        if not base_url:
            raise ValueError("LLMClient requires a non-empty base_url.")

        self.base_url = base_url
        self.api_key = api_key
        self.default_model = model
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = context_window - max_output_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        self._is_closed = False

    @abc.abstractmethod
    def _create_client(self):
        """
        Creates the appropriate OpenAI client instance.
        Must be implemented by subclasses.
        """
        pass

    def _ensure_client(self):
        """Ensures the client is initialized if not already."""
        if self._is_closed:
            raise RuntimeError("Cannot use client: LLMClient instance has been closed.")
        if self._client is None:
            self._client = self._create_client()
            logger.debug("Auto-initialized LLM client.")

    @abc.abstractmethod
    def close(self):
        """Close the client connection."""
        pass

    @abc.abstractmethod
    def get_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ):
        """
        Retrieves the full completion content from the LLM (non-streaming).
        Must be implemented by subclasses.
        """
        pass

    @abc.abstractmethod
    def stream_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ):
        """
        Retrieves the completion content from the LLM in streaming mode.
        Must be implemented by subclasses.
        """
        pass


class AsyncLLMClient(LLMClientBase):
    """
    Asynchronous client for interacting with Large Language Models.
    Uses AsyncOpenAI for all operations.
    """

    def _create_client(self) -> AsyncOpenAI:
        """Creates an AsyncOpenAI client instance."""
        if self._is_closed:
            raise RuntimeError(
                "Cannot create client: AsyncLLMClient instance has been closed."
            )

        logger.debug(f"Creating AsyncOpenAI client for {self.base_url}")
        return AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    async def close(self) -> None:
        """Closes the underlying AsyncOpenAI client connection."""
        if self._client and not self._is_closed:
            logger.info(f"Closing AsyncLLMClient connection to {self.base_url}")
            try:
                await self._client.close()
            except Exception as e:
                logger.error(f"Error closing AsyncLLMClient: {e}", exc_info=True)
            finally:
                self._client = None
                self._is_closed = True

    # --- Context Manager Support ---
    async def __aenter__(self):
        self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def get_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Asynchronously retrieves the full completion content from the LLM (non-streaming).

        Args:
            messages: List of messages forming the conversation history/prompt.
            model: Model name to use (overrides client default).
            max_output_tokens: Max tokens for the response.
            temperature: Sampling temperature (0.0-2.0).
            top_p: Nucleus sampling parameter.
            **kwargs: Additional valid parameters for the OpenAI API completions endpoint.

        Returns:
        The generated text content as a single string.

        Raises:
            RuntimeError: If completion cannot be obtained after retries.
            APIError: For non-retryable API errors.
            Exception: For other unexpected errors.
        """
        model_to_use = model or self.default_model
        if not model_to_use:
            raise ValueError("No model specified for LLM completion request.")

        self._ensure_client()
        client = cast(AsyncOpenAI, self._client)

        request_params = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            **kwargs,
        }
        request_params = {k: v for k, v in request_params.items() if v is not None}

        logger.debug(f"Requesting async completion from model '{model_to_use}'...")

        try:
            completion = await client.chat.completions.create(**request_params)

            # Log usage
            if completion.usage:
                logger.info(
                    f"LLM Usage (Model: {model_to_use}): "
                    f"Prompt={completion.usage.prompt_tokens}, "
                    f"Completion={completion.usage.completion_tokens}, "
                    f"Total={completion.usage.total_tokens}"
                )

            # Extract content
            if completion.choices and completion.choices[0].message:
                response_content = completion.choices[0].message.content
                finish_reason = completion.choices[0].finish_reason
                logger.debug(f"Completion received. Finish reason: {finish_reason}")
                return response_content if response_content is not None else ""
            else:
                logger.warning(
                    "LLM response received but no valid choice or message content found."
                )
                raise RuntimeError(
                    "LLM response received but no valid choice or message content found."
                )

        except (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
        ) as transient_error:
            logger.warning(f"Transient LLM API error: {transient_error}", exc_info=True)
            raise
        except APIError as api_error:
            logger.error(f"Non-retryable LLM API error: {api_error}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during LLM call: {e}", exc_info=True)
            raise

    async def stream_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams the completion content from the LLM.

        Args:
            messages: List of messages forming the conversation history/prompt.
            model: Model name to use (overrides client default).
            max_output_tokens: Max tokens for the response.
            temperature: Sampling temperature (0.0-2.0).
            top_p: Nucleus sampling parameter.
            **kwargs: Additional valid parameters for the OpenAI API completions endpoint.

        Yields:
            str: Chunks of the generated text content.

        Raises:
            RuntimeError: If the stream cannot be initiated after retries.
            APIError: For non-retryable API errors during streaming.
            Exception: For other unexpected errors during streaming.
        """
        model_to_use = model or self.default_model
        if not model_to_use:
            raise ValueError("No model specified for LLM streaming request.")

        self._ensure_client()
        client = cast(AsyncOpenAI, self._client)

        request_params = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            **kwargs,
        }
        request_params = {k: v for k, v in request_params.items() if v is not None}

        logger.debug(
            f"Requesting async streaming completion from model '{model_to_use}'..."
        )

        try:
            stream = await client.chat.completions.create(**request_params)
            logger.debug("Async LLM stream initiated.")

            # Process the stream
            total_chunks = 0
            async for chunk in stream:
                total_chunks += 1
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason
                    if delta and delta.content:
                        yield delta.content
                    if finish_reason:
                        logger.info(
                            f"LLM stream finished for model {model_to_use}. "
                            f"Reason: {finish_reason}. Total chunks: {total_chunks}"
                        )
                        # Log usage if available on the *last* chunk
                        if hasattr(chunk, "usage") and chunk.usage:
                            logger.info(
                                f"LLM API Usage (final chunk): "
                                f"Prompt={chunk.usage.prompt_tokens}, "
                                f"Completion={chunk.usage.completion_tokens}, "
                                f"Total={chunk.usage.total_tokens}"
                            )
                        break

            logger.debug(
                f"Async stream completed for model {model_to_use}, chunks: {total_chunks}"
            )
            return  # End the generator after stream is complete

        except (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
        ) as transient_error:
            logger.warning(
                f"Transient LLM API error initiating stream: {transient_error}",
                exc_info=True,
            )
            raise
        except APIError as api_error:
            logger.error(
                f"Non-retryable LLM API error initiating stream: {api_error}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error initiating stream: {e}", exc_info=True)
            raise


class SyncLLMClient(LLMClientBase):
    """
    Synchronous client for interacting with Large Language Models.
    Uses OpenAI for all operations.
    """

    def _create_client(self) -> OpenAI:
        """Creates an OpenAI client instance."""
        if self._is_closed:
            raise RuntimeError(
                "Cannot create client: SyncLLMClient instance has been closed."
            )

        logger.debug(f"Creating OpenAI client for {self.base_url}")
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,  # Disable automatic retries, handle manually
        )

    def close(self) -> None:
        """Closes the underlying OpenAI client connection."""
        if self._client and not self._is_closed:
            logger.info(f"Closing SyncLLMClient connection to {self.base_url}")
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Error closing SyncLLMClient: {e}", exc_info=True)
            finally:
                self._client = None
                self._is_closed = True

    # --- Context Manager Support ---
    def __enter__(self):
        self._ensure_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Synchronously retrieves the full completion content from the LLM (non-streaming).

        Args:
            messages: List of messages forming the conversation history/prompt.
            model: Model name to use (overrides client default).
            max_output_tokens: Max tokens for the response.
            temperature: Sampling temperature (0.0-2.0).
            top_p: Nucleus sampling parameter.
            **kwargs: Additional valid parameters for the OpenAI API completions endpoint.

        Returns:
            The generated text content as a single string.

        Raises:
            RuntimeError: If completion cannot be obtained after retries.
            APIError: For non-retryable API errors.
            Exception: For other unexpected errors.
        """
        model_to_use = model or self.default_model
        if not model_to_use:
            raise ValueError("No model specified for LLM completion request.")

        self._ensure_client()
        client = cast(OpenAI, self._client)

        request_params = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            **kwargs,
        }
        request_params = {k: v for k, v in request_params.items() if v is not None}

        logger.debug(f"Requesting sync completion from model '{model_to_use}'...")

        try:
            completion = client.chat.completions.create(**request_params)

            # Log usage
            if completion.usage:
                logger.info(
                    f"LLM Usage (Model: {model_to_use}): "
                    f"Prompt={completion.usage.prompt_tokens}, "
                    f"Completion={completion.usage.completion_tokens}, "
                    f"Total={completion.usage.total_tokens}"
                )

            # Extract content
            if completion.choices and completion.choices[0].message:
                response_content = completion.choices[0].message.content
                finish_reason = completion.choices[0].finish_reason
                logger.debug(f"Completion received. Finish reason: {finish_reason}")
                return response_content if response_content is not None else ""
            else:
                logger.warning(
                    "LLM response received but no valid choice or message content found."
                )
                raise RuntimeError(
                    "LLM response received but no valid choice or message content found."
                )

        except (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
        ) as transient_error:
            logger.warning(f"Transient LLM API error: {transient_error}", exc_info=True)
            raise
        except APIError as api_error:
            logger.error(f"Non-retryable LLM API error: {api_error}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during LLM call: {e}", exc_info=True)
            raise

    def stream_completion_content(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: Optional[float] = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        Synchronously streams the completion content from the LLM.

        Args:
            messages: List of messages forming the conversation history/prompt.
            model: Model name to use (overrides client default).
            max_output_tokens: Max tokens for the response.
            temperature: Sampling temperature (0.0-2.0).
            top_p: Nucleus sampling parameter.
            **kwargs: Additional valid parameters for the OpenAI API completions endpoint.

        Yields:
            str: Chunks of the generated text content.

        Raises:
            RuntimeError: If the stream cannot be initiated after retries.
            APIError: For non-retryable API errors during streaming.
            Exception: For other unexpected errors during streaming.
        """
        model_to_use = model or self.default_model
        if not model_to_use:
            raise ValueError("No model specified for LLM streaming request.")

        self._ensure_client()
        client = cast(OpenAI, self._client)

        request_params = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            **kwargs,
        }
        request_params = {k: v for k, v in request_params.items() if v is not None}

        logger.debug(
            f"Requesting sync streaming completion from model '{model_to_use}'..."
        )

        try:
            stream = client.chat.completions.create(**request_params)
            logger.debug("Sync LLM stream initiated.")

            # Process the stream
            total_chunks = 0
            for chunk in stream:
                total_chunks += 1
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason
                    if delta and delta.content:
                        yield delta.content
                    if finish_reason:
                        logger.info(
                            f"LLM stream finished for model {model_to_use}. "
                            f"Reason: {finish_reason}. Total chunks: {total_chunks}"
                        )
                        if hasattr(chunk, "usage") and chunk.usage:
                            logger.info(
                                f"LLM API Usage (final chunk): "
                                f"Prompt={chunk.usage.prompt_tokens}, "
                                f"Completion={chunk.usage.completion_tokens}, "
                                f"Total={chunk.usage.total_tokens}"
                            )
                        break

            logger.debug(
                f"Sync stream completed for model {model_to_use}, chunks: {total_chunks}"
            )
            return  # End the generator after stream is complete

        except (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
        ) as transient_error:
            logger.warning(
                f"Transient LLM API error initiating stream: {transient_error}",
                exc_info=True,
            )
            raise
        except APIError as api_error:
            logger.error(
                f"Non-retryable LLM API error initiating stream: {api_error}",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error initiating stream: {e}", exc_info=True)
            raise


# Factory function for backward compatibility
def LLMClient(
    base_url: str,
    api_key: Optional[str],
    async_mode: bool = True,
    model: Optional[str] = None,
    context_window: int = 4096,
    max_output_tokens: int = 2048,
    timeout: int = 600,
    max_retries: int = 3,
) -> Union[AsyncLLMClient, SyncLLMClient]:
    """
    Factory function to create an appropriate LLM client.

    Args:
        base_url: The base URL of the LLM API.
        api_key: The API key for authentication.
        async_mode: If True, creates AsyncLLMClient, otherwise SyncLLMClient.
        model: Default model name to use if not specified in methods.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries for transient API errors.

    Returns:
        Either AsyncLLMClient or SyncLLMClient based on async_mode.
    """
    if async_mode:
        return AsyncLLMClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )
    else:
        return SyncLLMClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )
