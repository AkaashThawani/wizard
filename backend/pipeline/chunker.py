"""
pipeline/chunker.py

Sentence-boundary detection and segmentation.

Rules:
- Segments always start and end at sentence boundaries.
- Sentence boundary = word immediately after a punctuation mark
  (. ! ?) with confidence > 0.8 preferred.
- If no high-confidence boundary is found, fall back to any punctuation boundary.
- Minimum segment duration: 1.0 second (merge tiny trailing fragments).

Pure Python — no ML, no external dependencies.
"""

from __future__ import annotations

import re
import uuid
from timeline.models import Segment, WordToken

# Sentence-ending punctuation
SENTENCE_END_RE = re.compile(r"[.!?]+$")

MIN_SEGMENT_DURATION = 1.0   # seconds
HIGH_CONFIDENCE = 0.8


def _is_sentence_end(word: str) -> bool:
    """True if the word ends with sentence-ending punctuation."""
    return bool(SENTENCE_END_RE.search(word.strip()))


def chunk_segments(
    segments: list[Segment],
    min_duration: float = MIN_SEGMENT_DURATION,
) -> list[Segment]:
    """
    Re-chunk a list of segments into sentence-aligned segments.

    Input segments may span multiple sentences or start mid-sentence.
    This function uses word-level timestamps to find sentence boundaries
    and produces new Segment objects aligned to complete sentences.
    """
    # Flatten all words from all segments into one ordered list
    all_words: list[WordToken] = []
    source = segments[0].source if segments else ""
    for seg in segments:
        all_words.extend(seg.words)

    if not all_words:
        return segments  # nothing to do

    # Find sentence boundary indices (index of last word in each sentence)
    boundary_indices = _find_boundaries(all_words)

    # Build new segments from boundaries
    new_segments = _build_from_boundaries(all_words, boundary_indices, source)

    # Merge short trailing fragments
    new_segments = _merge_short(new_segments, min_duration)

    return new_segments


def _find_boundaries(words: list[WordToken]) -> list[int]:
    """
    Return a list of indices (into words) where sentences end.

    Prefer high-confidence boundary words.
    Always include the last word as a boundary.
    """
    boundaries: list[int] = []

    # First pass: high-confidence sentence ends
    for i, w in enumerate(words):
        if _is_sentence_end(w.word) and w.confidence >= HIGH_CONFIDENCE:
            boundaries.append(i)

    # If no high-confidence boundaries, fall back to any punctuation
    if not boundaries:
        for i, w in enumerate(words):
            if _is_sentence_end(w.word):
                boundaries.append(i)

    # Always end at the last word
    last_idx = len(words) - 1
    if not boundaries or boundaries[-1] != last_idx:
        boundaries.append(last_idx)

    return boundaries


def _build_from_boundaries(
    words: list[WordToken],
    boundaries: list[int],
    source: str,
) -> list[Segment]:
    segments: list[Segment] = []
    prev = 0

    for boundary in boundaries:
        chunk = words[prev:boundary + 1]
        if not chunk:
            prev = boundary + 1
            continue

        text = " ".join(w.word for w in chunk).strip()
        start = chunk[0].start
        end = chunk[-1].end
        duration = end - start

        if duration <= 0:
            prev = boundary + 1
            continue

        segments.append(Segment(
            id=f"seg_{uuid.uuid4().hex[:8]}",
            start=start,
            end=end,
            duration=duration,
            text=text,
            words=chunk,
            speaker=None,
            source=source,
            chroma_id="",
        ))
        prev = boundary + 1

    return segments


def _merge_short(
    segments: list[Segment],
    min_duration: float,
) -> list[Segment]:
    """Merge segments shorter than min_duration into the preceding segment."""
    if len(segments) <= 1:
        return segments

    result: list[Segment] = []
    for seg in segments:
        if result and seg.duration < min_duration:
            prev = result[-1]
            merged_words = prev.words + seg.words
            merged_text = prev.text + " " + seg.text
            result[-1] = Segment(
                id=prev.id,
                start=prev.start,
                end=seg.end,
                duration=seg.end - prev.start,
                text=merged_text.strip(),
                words=merged_words,
                speaker=prev.speaker,
                source=prev.source,
                chroma_id="",
            )
        else:
            result.append(seg)

    return result


def find_word_boundary(
    segment: Segment,
    offset: float,
    prefer_high_confidence: bool = True,
) -> float:
    """
    Snap an offset (seconds relative to segment start) to the nearest
    WordToken boundary.

    Used by EditAgent.trim_segment to enforce clean cuts.
    Returns the snapped offset (still relative to segment start).
    """
    if not segment.words:
        return offset

    absolute = segment.start + offset

    # Find nearest word boundary
    candidates = []
    for w in segment.words:
        dist_start = abs(w.start - absolute)
        dist_end = abs(w.end - absolute)
        best_dist = min(dist_start, dist_end)
        boundary_time = w.start if dist_start <= dist_end else w.end
        candidates.append((best_dist, w.confidence, boundary_time))

    if prefer_high_confidence:
        # Prefer high-confidence words within 0.5s, otherwise nearest
        high_conf = [c for c in candidates if c[1] >= HIGH_CONFIDENCE]
        if high_conf:
            candidates = high_conf

    candidates.sort(key=lambda c: c[0])
    snapped_absolute = candidates[0][2]
    return snapped_absolute - segment.start
