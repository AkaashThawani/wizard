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
    silence_threshold: float = 0.5,
    max_segment_duration: float = 8.0,
) -> list[Segment]:
    """
    Re-chunk a list of segments into sentence-aligned segments.

    Input segments may span multiple sentences or start mid-sentence.
    This function uses word-level timestamps to find sentence boundaries
    and natural pauses (silence gaps) to create segments.
    
    Args:
        segments: Input segments from Whisper
        min_duration: Minimum segment duration (merge shorter ones)
        silence_threshold: Gap threshold for splitting (seconds)
        max_segment_duration: Force split if segment exceeds this duration
    
    Returns:
        List of re-chunked segments with natural boundaries
    """
    # Flatten all words from all segments into one ordered list
    all_words: list[WordToken] = []
    source = segments[0].source if segments else ""
    for seg in segments:
        all_words.extend(seg.words)

    if not all_words:
        # ONNX fallback: chunk by text only (no word timestamps)
        print(f"⚠️  No word-level timestamps - using text-based chunking")
        return _chunk_by_text_only(segments, min_duration)

    # Find sentence boundary indices (index of last word in each sentence)
    boundary_indices = _find_boundaries(all_words, silence_threshold, max_segment_duration)

    # Build new segments from boundaries
    new_segments = _build_from_boundaries(all_words, boundary_indices, source)

    # Merge short trailing fragments
    new_segments = _merge_short(new_segments, min_duration)

    return new_segments


def _find_boundaries(
    words: list[WordToken],
    silence_threshold: float = 0.5,
    max_segment_duration: float = 8.0,
) -> list[int]:
    """
    Return a list of indices (into words) where segments should end.

    Uses multiple strategies to find natural boundaries:
    1. High-confidence sentence endings (. ! ? with confidence > 0.8)
    2. Timing gaps between words (silence > threshold)
    3. Maximum segment duration (force split if too long)
    
    Args:
        words: List of word tokens with timestamps
        silence_threshold: Minimum gap to consider as silence (seconds)
        max_segment_duration: Maximum segment length before forced split
    
    Returns:
        Sorted list of word indices where segments should end
    """
    boundaries: set[int] = set()
    last_idx = len(words) - 1

    # Strategy 1: High-confidence sentence endings
    for i, w in enumerate(words):
        if _is_sentence_end(w.word) and w.confidence >= HIGH_CONFIDENCE:
            boundaries.add(i)

    # Strategy 2: Timing gaps (silence detection)
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap >= silence_threshold:
            # Found a silence gap - mark as boundary
            boundaries.add(i)

    # Strategy 3: Maximum duration enforcement
    # Track current segment duration and force split if too long
    segment_start = 0
    for i in range(len(words)):
        if i > 0:
            duration = words[i].end - words[segment_start].start
            if duration >= max_segment_duration:
                # Segment too long - find nearest boundary
                # Prefer sentence end or silence gap
                for j in range(i - 1, segment_start, -1):
                    if j in boundaries:
                        segment_start = j + 1
                        break
                else:
                    # No natural boundary found - force split here
                    boundaries.add(i)
                    segment_start = i + 1

    # If no boundaries found, fall back to any punctuation
    if not boundaries:
        for i, w in enumerate(words):
            if _is_sentence_end(w.word):
                boundaries.add(i)

    # Always end at the last word
    boundaries.add(last_idx)

    # Return sorted list
    return sorted(boundaries)


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


def _chunk_by_text_only(
    segments: list[Segment],
    min_duration: float,
) -> list[Segment]:
    """
    Fallback chunking for ONNX Whisper (no word-level timestamps).
    
    Splits segments by sentence boundaries using text punctuation.
    Estimates timing by distributing segment duration proportionally.
    
    Args:
        segments: Input segments with chunk-level timestamps only
        min_duration: Minimum segment duration (merge shorter ones)
    
    Returns:
        List of sentence-aligned segments
    """
    result_segments = []
    
    for seg in segments:
        if not seg.text or not seg.text.strip():
            result_segments.append(seg)
            continue
        
        # Split text by sentence-ending punctuation
        sentences = re.split(r'([.!?]+)', seg.text)
        
        # Reconstruct sentences with their punctuation
        sentence_texts = []
        i = 0
        while i < len(sentences):
            text = sentences[i].strip()
            if not text:
                i += 1
                continue
            
            # Add punctuation if next element is punctuation
            if i + 1 < len(sentences) and sentences[i + 1].strip() in '.!?':
                text += sentences[i + 1]
                i += 2
            else:
                i += 1
            
            if text:
                sentence_texts.append(text)
        
        # If no sentence splits found, keep original segment
        if len(sentence_texts) <= 1:
            result_segments.append(seg)
            continue
        
        # Estimate timing by word count (proportional distribution)
        total_words = sum(len(s.split()) for s in sentence_texts)
        current_time = seg.start
        
        for sentence_text in sentence_texts:
            # Estimate duration based on word count proportion
            word_count = len(sentence_text.split())
            if total_words > 0:
                proportion = word_count / total_words
                estimated_duration = seg.duration * proportion
            else:
                estimated_duration = seg.duration / len(sentence_texts)
            
            sentence_end = current_time + estimated_duration
            
            # Create new segment for this sentence
            new_seg = Segment(
                id=f"seg_{uuid.uuid4().hex[:8]}",
                start=current_time,
                end=sentence_end,
                duration=estimated_duration,
                text=sentence_text.strip(),
                words=[],  # No word-level data
                speaker=seg.speaker,
                source=seg.source,
                chroma_id="",
            )
            
            result_segments.append(new_seg)
            current_time = sentence_end
    
    # Merge segments shorter than min_duration
    result_segments = _merge_short(result_segments, min_duration)
    
    print(f"✓ Text-based chunking: {len(segments)} → {len(result_segments)} segments")
    
    return result_segments


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
