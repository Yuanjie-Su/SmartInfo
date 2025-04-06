# -*- coding: utf-8 -*-
# (Content is identical to the original src/core/llm/utils.py)
# Just ensure the file is moved to src/utils/token_utils.py

# Requires installing the deepseek tokenizer: pip install deepseek-tokenizer
try:
    from deepseek_tokenizer import ds_token
except ImportError:
    ds_token = None
    print(
        "Warning: deepseek-tokenizer not installed. Token size calculation for deepseek models will not work."
    )
    print("Please run: pip install deepseek-tokenizer")

import logging

logger = logging.getLogger(__name__)


def get_token_size(text: str, model_type: str = "deepseek") -> int:
    """
    Calculates the token size of the given text using the specified tokenizer.

    Args:
        text: The text to calculate the token size of.
        model_type: The type of model tokenizer to use (currently only 'deepseek' supported).

    Returns:
        The estimated token size of the text, or 0 if tokenizer is unavailable or fails.
    """

    if model_type == "deepseek":
        if ds_token:
            try:
                # Ensure text is string
                if not isinstance(text, str):
                    text = str(text)
                return len(ds_token.encode(text))
            except Exception as e:
                logger.warning(
                    f"Deepseek tokenizer failed for text starting with '{text[:50]}...': {e}. Returning 0."
                )
                return 0
        else:
            logger.warning(
                "Deepseek tokenizer is not available. Cannot calculate token size."
            )
            return 0
    else:
        logger.warning(
            f"Tokenizer for model type '{model_type}' is not supported. Returning 0."
        )
        return 0
