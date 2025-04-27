# src/utils/text_utils.py
# -*- coding: utf-8 -*-
"""
Text utility functions for content processing and manipulation
"""
from typing import List
import re


def get_chunks(text: str, num_chunks: int) -> List[str]:
    """
    Split the input text into roughly equal-sized chunks by []() pair count.
    
    Args:
        text: The text to split into chunks
        num_chunks: The number of chunks to create
        
    Returns:
        A list of text chunks as strings
    """
    # Find all []() patterns in the text
    pattern = r'\[.*?\]\(.*?\)'
    matches = list(re.finditer(pattern, text))
    
    if not matches:
        return []

    total_pairs = len(matches)
    
    # Calculate how many pairs should go in each chunk
    pairs_per_chunk = max(1, total_pairs // num_chunks)
    chunks: List[str] = []
    
    # Adjust the number of chunks if necessary
    actual_num_chunks = min(num_chunks, total_pairs)
    
    for i in range(actual_num_chunks):
        # Calculate start and end indices for this chunk
        start_pair_idx = i * pairs_per_chunk
        
        # For the last chunk, include all remaining pairs
        if i == actual_num_chunks - 1:
            end_pair_idx = total_pairs
        else:
            end_pair_idx = min((i + 1) * pairs_per_chunk, total_pairs)
        
        # Skip if no pairs in this chunk
        if start_pair_idx >= total_pairs:
            break
            
        # Determine text positions
        # For first chunk, start from beginning of text
        if start_pair_idx == 0:
            start_pos = 0
        else:
            # Otherwise start from position of the first pattern in this chunk
            start_pos = matches[start_pair_idx].start()
            
        # For last chunk or if this chunk includes the last pair, go to end of text
        if end_pair_idx >= total_pairs:
            end_pos = len(text)
        else:
            # Otherwise end at start of next chunk's first pattern
            end_pos = matches[end_pair_idx].start()
            
        chunk = text[start_pos:end_pos]
        if chunk.strip():
            chunks.append(chunk)
    
    # Special case: if we have pairs but didn't create any chunks, return the whole text
    if total_pairs > 0 and not chunks:
        return [text]
    
    return chunks
