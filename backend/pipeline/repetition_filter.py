"""
pipeline/repetition_filter.py

Remove repetitive word sequences from transcription text.

Whisper sometimes hallucinates repetitive patterns, especially during
applause or background noise (e.g., "Thank you very much" x30).

This filter detects and caps repetitive sequences at a maximum count.
"""

from __future__ import annotations

import re
from timeline.models import Segment


def remove_repetition(text: str, max_repeat: int = 5) -> str:
    """
    Remove excessive repetition from text.
    
    Detects patterns like "thank you" repeated 30 times and caps at max_repeat.
    
    Args:
        text: Input text with potential repetition
        max_repeat: Maximum allowed repetitions of any phrase (default: 5)
    
    Returns:
        Text with repetition capped
    
    Examples:
        >>> remove_repetition("Thank you. Thank you. Thank you. Thank you. Thank you. Thank you.", max_repeat=3)
        "Thank you. Thank you. Thank you."
        
        >>> remove_repetition("Hello world. Hello world. Hello world. Hello world.", max_repeat=2)
        "Hello world. Hello world."
    """
    if not text or not text.strip():
        return text
    
    # Split into sentences (basic split on punctuation)
    sentences = re.split(r'([.!?]+\s*)', text)
    
    # Rebuild with de-duplication
    result = []
    prev_sentence = None
    repeat_count = 0
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i].strip()
        if i + 1 < len(sentences):
            punctuation = sentences[i + 1]
        else:
            punctuation = ""
        
        if not sentence:
            continue
        
        # Check if this is a repeat of previous sentence
        if sentence.lower() == prev_sentence:
            repeat_count += 1
            if repeat_count < max_repeat:
                result.append(sentence + punctuation)
        else:
            # New sentence - reset counter
            result.append(sentence + punctuation)
            prev_sentence = sentence.lower()
            repeat_count = 0
    
    return " ".join(result).strip()


def filter_segment_repetition(segments: list[Segment], max_repeat: int = 5) -> list[Segment]:
    """
    Apply repetition filtering to all segments.
    
    Args:
        segments: List of segments to filter
        max_repeat: Maximum allowed repetitions
    
    Returns:
        Segments with filtered text
    """
    for seg in segments:
        if seg.text:
            seg.text = remove_repetition(seg.text, max_repeat=max_repeat)
    
    return segments
