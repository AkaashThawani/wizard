"""
pipeline/merger.py

Merges adjacent Whisper segments that are separated by short silences.

Whisper tends to produce many short segments. This step consolidates them
before chunking into sentence-aligned units.

Pure Python — no ML, no external dependencies.
"""

from __future__ import annotations

from timeline.models import Segment, WordToken
import uuid

DEFAULT_SILENCE_THRESHOLD = 0.5   # seconds — merge if gap < this


def merge_segments(
    segments: list[Segment],
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
) -> list[Segment]:
    """
    Merge adjacent segments whose inter-segment gap is below the threshold.

    Uses word-level timestamps for precise gap detection.

    Returns a new list of merged Segment objects. Each merged segment:
    - id: new UUID
    - start: start of first constituent segment
    - end: end of last constituent segment
    - text: concatenated texts (space-joined)
    - words: concatenated word lists
    - speaker: kept if all constituents share the same speaker; else None
    - source: taken from first constituent
    - chroma_id: empty (assigned later by vectorizer)
    """
    if not segments:
        return []

    groups: list[list[Segment]] = [[segments[0]]]

    for seg in segments[1:]:
        last_group = groups[-1]
        last_seg = last_group[-1]

        # Compute gap using word-level timestamps if available
        if last_seg.words and seg.words:
            gap = seg.words[0].start - last_seg.words[-1].end
        else:
            gap = seg.start - last_seg.end

        if gap < silence_threshold:
            last_group.append(seg)
        else:
            groups.append([seg])

    return [_merge_group(g) for g in groups]


def _merge_group(group: list[Segment]) -> Segment:
    if len(group) == 1:
        return group[0]

    first = group[0]
    last = group[-1]

    all_words: list[WordToken] = []
    texts: list[str] = []
    speakers: set[str | None] = set()

    for seg in group:
        all_words.extend(seg.words)
        texts.append(seg.text)
        speakers.add(seg.speaker)

    speaker = speakers.pop() if len(speakers) == 1 else None

    merged_text = " ".join(t.strip() for t in texts if t.strip())
    start = first.start
    end = last.end
    duration = end - start

    return Segment(
        id=f"seg_{uuid.uuid4().hex[:8]}",
        start=start,
        end=end,
        duration=duration,
        text=merged_text,
        words=all_words,
        speaker=speaker,
        source=first.source,
        chroma_id="",
    )


def whisper_output_to_segments(
    raw_segments: list[dict],
    source_path: str,
) -> list[Segment]:
    """
    Convert faster-whisper segment output into Segment objects.

    Each raw_segment dict from faster-whisper has:
      - start, end, text, words (list of dicts with word/start/end/probability)
    """
    from timeline.models import WordToken
    result: list[Segment] = []

    for raw in raw_segments:
        words: list[WordToken] = []
        for w in raw.get("words", []):
            words.append(WordToken(
                word=w.get("word", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
                confidence=w.get("probability", 1.0),
            ))

        start = raw.get("start", 0.0)
        end = raw.get("end", 0.0)

        result.append(Segment(
            id=f"seg_{uuid.uuid4().hex[:8]}",
            start=start,
            end=end,
            duration=end - start,
            text=raw.get("text", "").strip(),
            words=words,
            speaker=raw.get("speaker"),
            source=source_path,
            chroma_id="",
        ))

    return result
