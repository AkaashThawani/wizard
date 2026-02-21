"""
pipeline/cleaner.py

Removes filler words and deduplicates repeated phrases from a WordToken list.

Pure Python — no ML, no external dependencies.
"""

from __future__ import annotations

import re
from timeline.models import WordToken

# Configurable filler-word list
DEFAULT_FILLERS = {
    "um", "uh", "er", "ah", "hmm", "hm",
    "like", "you know", "i mean", "right",
    "basically", "literally", "actually", "so",
}


def remove_fillers(
    tokens: list[WordToken],
    fillers: set[str] | None = None,
) -> list[WordToken]:
    """
    Remove filler words from a token list.

    Filler matching is case-insensitive and whole-word only.
    Short stand-alone words that are in the filler set are removed.
    """
    if fillers is None:
        fillers = DEFAULT_FILLERS

    result: list[WordToken] = []
    for tok in tokens:
        word_clean = tok.word.strip().lower().strip(".,!?;:")
        if word_clean in fillers:
            continue
        result.append(tok)
    return result


def deduplicate_phrases(
    tokens: list[WordToken],
    window: int = 6,
) -> list[WordToken]:
    """
    Remove immediately repeated phrases.

    Scans a sliding window of `window` words; if a sequence appears twice
    consecutively, the second occurrence is dropped.

    Example: ["I", "think", "I", "think", "it", "works"]
             → ["I", "think", "it", "works"]
    """
    if len(tokens) < 2:
        return tokens

    result: list[WordToken] = list(tokens)
    changed = True

    # Iterate until no more changes (handles cascading duplicates)
    while changed:
        changed = False
        new_result: list[WordToken] = []
        i = 0
        while i < len(result):
            # Try window sizes from largest to smallest
            found = False
            for w in range(min(window, len(result) - i) // 2, 0, -1):
                seq = [t.word.lower() for t in result[i:i + w]]
                next_seq = [t.word.lower() for t in result[i + w:i + 2 * w]]
                if seq == next_seq and len(seq) > 0:
                    # Keep first occurrence, skip second
                    new_result.extend(result[i:i + w])
                    i += 2 * w
                    changed = True
                    found = True
                    break
            if not found:
                new_result.append(result[i])
                i += 1
        result = new_result

    return result


def clean(
    tokens: list[WordToken],
    fillers: set[str] | None = None,
    dedup_window: int = 6,
) -> list[WordToken]:
    """
    Full cleaning pass: remove fillers, then deduplicate repeated phrases.
    """
    tokens = remove_fillers(tokens, fillers)
    tokens = deduplicate_phrases(tokens, dedup_window)
    return tokens
