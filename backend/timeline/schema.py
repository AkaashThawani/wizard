"""
timeline/schema.py

String constants, ownership map, and enums used throughout the timeline layer.
"""

from enum import Enum


class TimelineKeys:
    """String keys used in the timeline JSON structure."""
    SOURCE = "source"
    SEGMENT_POOL = "segment_pool"
    LAYERS = "layers"
    AGENT_DATA = "agent_data"
    SNAPSHOTS = "snapshots"
    CURRENT = "current"
    HISTORY = "history"
    SEQUENCE = "sequence"
    SNAPSHOT_REF = "snapshot_ref"

    # Source sub-keys
    SOURCE_PATH = "path"
    SOURCE_FILENAME = "filename"
    SOURCE_DURATION = "duration"

    # Segment sub-keys
    SEG_ID = "id"
    SEG_START = "start"
    SEG_END = "end"
    SEG_DURATION = "duration"
    SEG_TEXT = "text"
    SEG_WORDS = "words"
    SEG_SPEAKER = "speaker"
    SEG_SOURCE = "source"
    SEG_CHROMA_ID = "chroma_id"

    # EditLayer sub-keys
    TRIM = "trim"
    EFFECTS = "effects"
    TRIM_START = "start"
    TRIM_END = "end"

    # Transition sub-keys
    TRANSITION_TYPE = "type"
    TRANSITION_DURATION = "duration_s"

    # History sub-keys
    HIST_PROMPT = "prompt"
    HIST_SUMMARY = "summary"
    HIST_SNAPSHOT_REF = "snapshot_ref"


# Map: which agent owns which layer key.
# Agents must only write to their own layer.
AGENT_OWNS: dict[str, str] = {
    "transcription_agent": "transcription_agent",
    "search_agent": "search_agent",
    "edit_agent": "edit_agent",
    "export_agent": "export_agent",
    "color_agent": "color_agent",
    "audio_agent": "audio_agent",
}


class EffectType(str, Enum):
    """Supported per-segment effect types (v1)."""
    VOLUME = "volume"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    MUTE = "mute"
    CAPTION = "caption"
    SPEED = "speed"
    CROP = "crop"


class TransitionType(str, Enum):
    """Supported transition types between segments."""
    CUT = "cut"
    CROSSFADE = "crossfade"
    DISSOLVE = "dissolve"
