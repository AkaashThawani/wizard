"""
timeline/models.py

Dataclasses for all timeline entities.
All dataclasses are JSON-serialisable via dataclasses.asdict().
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any

from timeline.schema import EffectType, TransitionType


# ---------------------------------------------------------------------------
# Primitive building blocks
# ---------------------------------------------------------------------------

@dataclass
class WordToken:
    """A single word with its source timecode and Whisper confidence."""
    word: str
    start: float       # seconds from video start
    end: float
    confidence: float  # 0.0–1.0 from Whisper


@dataclass
class Segment:
    """
    An immutable unit of speech in the segment_pool.

    Segments always start and end at sentence boundaries (enforced by the
    chunker). They are never deleted; they are only included or excluded from
    current.sequence.
    """
    id: str                        # stable UUID — never changes
    start: float                   # source timecode (seconds)
    end: float                     # source timecode (seconds)
    duration: float
    text: str                      # full sentence text
    words: list[WordToken]         # word-level detail — never sent to LLM
    speaker: str | None
    source: str                    # path to source file
    chroma_id: str = ""            # populated by vectorizer
    is_silent: bool = False        # True for non-speech segments


# ---------------------------------------------------------------------------
# Sequence / current edit
# ---------------------------------------------------------------------------

@dataclass
class Transition:
    type: TransitionType
    duration_s: float


@dataclass
class SequenceEntry:
    segment_id: str
    transition_in: Transition | None = None


# ---------------------------------------------------------------------------
# Effects (non-destructive, per-segment)
# ---------------------------------------------------------------------------

@dataclass
class Effect:
    type: EffectType
    params: dict = field(default_factory=dict)
    enabled: bool = True


@dataclass
class EditLayer:
    """
    Everything EditAgent writes for a single segment.
    Lives at layers["edit_agent"][segment_id].
    """
    trim_start: float | None = None   # seconds relative to segment start
    trim_end: float | None = None     # seconds relative to segment start
    effects: list[Effect] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Snapshots and history
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    snap_id: str
    sequence: list[dict]   # serialised SequenceEntry list
    timestamp: str         # ISO-8601


@dataclass
class HistoryEntry:
    prompt: str
    summary: str
    snapshot_ref: str


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

class TimelineEncoder(json.JSONEncoder):
    """JSON encoder that handles Enum members and nested dataclasses."""
    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if isinstance(o, (EffectType, TransitionType)):
            return o.value
        return super().default(o)


def segment_to_dict(seg: Segment) -> dict:
    d = dataclasses.asdict(seg)
    return d


def segment_from_dict(d: dict) -> Segment:
    words = [WordToken(**w) for w in d.get("words", [])]
    return Segment(
        id=d["id"],
        start=d["start"],
        end=d["end"],
        duration=d["duration"],
        text=d["text"],
        words=words,
        speaker=d.get("speaker"),
        source=d["source"],
        chroma_id=d.get("chroma_id", ""),
        is_silent=d.get("is_silent", False),
    )


def sequence_entry_to_dict(e: SequenceEntry) -> dict:
    result: dict = {"segment_id": e.segment_id, "transition_in": None}
    if e.transition_in is not None:
        result["transition_in"] = {
            "type": e.transition_in.type.value,
            "duration_s": e.transition_in.duration_s,
        }
    return result


def sequence_entry_from_dict(d: dict) -> SequenceEntry:
    t = None
    if d.get("transition_in"):
        t = Transition(
            type=TransitionType(d["transition_in"]["type"]),
            duration_s=d["transition_in"]["duration_s"],
        )
    return SequenceEntry(segment_id=d["segment_id"], transition_in=t)


def effect_to_dict(e: Effect) -> dict:
    return {"type": e.type.value, "params": e.params, "enabled": e.enabled}


def effect_from_dict(d: dict) -> Effect:
    return Effect(type=EffectType(d["type"]), params=d.get("params", {}), enabled=d.get("enabled", True))


def edit_layer_to_dict(el: EditLayer) -> dict:
    return {
        "trim": {"start": el.trim_start, "end": el.trim_end},
        "effects": [effect_to_dict(e) for e in el.effects],
    }


def edit_layer_from_dict(d: dict) -> EditLayer:
    trim = d.get("trim", {})
    effects = [effect_from_dict(e) for e in d.get("effects", [])]
    return EditLayer(
        trim_start=trim.get("start"),
        trim_end=trim.get("end"),
        effects=effects,
    )
