"""
orchestrator/graph_types.py

Type definitions for LangGraph orchestration.

Defines the state schema that flows through the agent graph, including
phase tracking for progressive execution and checkpoint metadata for
SSE reconnection support.
"""

from typing import TypedDict, Annotated, Sequence, Literal
from dataclasses import dataclass
from operator import add


class AgentState(TypedDict):
    """
    State that flows through the LangGraph.
    
    Progressive execution phases:
    - "transcription": Transcribing video, extracting segments
    - "analysis": Visual and audio analysis (parallel)
    - "complete": All processing done
    """
    # User input (required)
    prompt: str
    project_id: str
    
    # Execution phase tracking (required)
    phase: Literal["transcription", "analysis", "complete"]
    
    # Phase completion flags (required)
    transcription_done: bool
    segments_count: int
    color_done: bool
    audio_done: bool
    
    # Per-second timeline data (optional - used in 3-way parallel workflow)
    visual_timeline: list[dict] | None
    visual_timeline_done: bool | None
    audio_timeline: list[dict] | None
    audio_timeline_done: bool | None
    
    # Connection tracking for SSE reconnection (optional)
    client_id: str | None
    last_checkpoint: str | None
    
    # Tool execution (required)
    tool_calls: list[dict]  # List of {name: str, params: dict}
    results: list[dict]     # List of {success: bool, data: dict, error: str | None}
    
    # Conversation history (optional)
    messages: Sequence[dict]
    
    # Execution metadata (required)
    snapshot_id: str | None
    success: bool
    error: Annotated[list[str], add] | None  # Collects errors from parallel nodes
    summary: str | None


@dataclass
class CheckpointMetadata:
    """
    Metadata stored with each checkpoint for resumption.
    """
    checkpoint_id: str
    phase: Literal["transcription", "analysis", "complete"]
    transcription_done: bool
    color_done: bool
    audio_done: bool
    segments_count: int
    timestamp: float
    
    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "phase": self.phase,
            "transcription_done": self.transcription_done,
            "color_done": self.color_done,
            "audio_done": self.audio_done,
            "segments_count": self.segments_count,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointMetadata":
        return cls(**data)


@dataclass
class SSEEvent:
    """
    Server-sent event structure.
    """
    event: str  # Event type: connected, transcription_progress, etc.
    data: dict  # Event payload
    checkpoint_id: str | None = None
    
    def to_json(self) -> dict:
        return {
            "event": self.event,
            "data": self.data,
            "checkpoint_id": self.checkpoint_id,
        }
