"""
timeline/state.py

TimelineState — the shared blackboard for all agents.

Design rules:
- segment_pool only grows (append-only).
- Agents write only to their own layer namespace.
- Snapshots capture current.sequence so any prompt can be rolled back.
- to_llm_context() returns a lean dict — no full transcripts, no embeddings.
- save() is called after every mutation; load() is called on __init__.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from timeline.models import (
    Segment, SequenceEntry, Snapshot, HistoryEntry,
    segment_to_dict, segment_from_dict,
    sequence_entry_to_dict, sequence_entry_from_dict,
)


class TimelineState:
    """
    The central blackboard shared by all agents.

    Persisted to projects/{project_id}/timeline.json after every mutation.
    """

    def __init__(self, project_id: str, projects_dir: str = "projects") -> None:
        self.project_id = project_id
        self.projects_dir = Path(projects_dir)
        self._path = self.projects_dir / project_id / "timeline.json"

        # In-memory state
        self._data: dict = self._empty_state()

        if self._path.exists():
            self.load()
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self.save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _empty_state(self) -> dict:
        return {
            "source": {},
            "segment_pool": {},
            "layers": {},
            "agent_data": {},
            "snapshots": {},
            "current": {
                "sequence": [],
                "snapshot_ref": None,
            },
            "history": [],
            "errors": [],
        }

    # ------------------------------------------------------------------
    # Source info
    # ------------------------------------------------------------------

    def set_source(self, path: str, filename: str, duration: float) -> None:
        self._data["source"] = {
            "path": path,
            "filename": filename,
            "duration": duration,
        }
        self.save()

    def get_source(self) -> dict:
        return self._data.get("source", {})

    # ------------------------------------------------------------------
    # Segment pool (append-only)
    # ------------------------------------------------------------------

    def add_segment(self, segment: Segment) -> None:
        """Append a segment to the pool. Never call this to delete."""
        self._data["segment_pool"][segment.id] = segment_to_dict(segment)
        self.save()

    def add_segments(self, segments: list[Segment]) -> None:
        for seg in segments:
            self._data["segment_pool"][seg.id] = segment_to_dict(seg)
        self.save()

    def get_segment(self, segment_id: str) -> Segment | None:
        raw = self._data["segment_pool"].get(segment_id)
        if raw is None:
            return None
        return segment_from_dict(raw)

    def get_all_segments(self) -> dict[str, Segment]:
        return {sid: segment_from_dict(raw) for sid, raw in self._data["segment_pool"].items()}

    def update_segment_chroma_id(self, segment_id: str, chroma_id: str) -> None:
        if segment_id in self._data["segment_pool"]:
            self._data["segment_pool"][segment_id]["chroma_id"] = chroma_id
        self.save()

    # ------------------------------------------------------------------
    # Current sequence
    # ------------------------------------------------------------------

    def get_current_sequence(self) -> list[SequenceEntry]:
        raw = self._data["current"]["sequence"]
        return [sequence_entry_from_dict(e) for e in raw]

    def set_sequence(self, entries: list[SequenceEntry]) -> None:
        self._data["current"]["sequence"] = [sequence_entry_to_dict(e) for e in entries]
        self.save()

    # ------------------------------------------------------------------
    # Layers — agent-namespaced key-value store
    # ------------------------------------------------------------------

    def get_layer(self, agent_name: str, segment_id: str) -> dict:
        return (
            self._data["layers"]
            .get(agent_name, {})
            .get(segment_id, {})
        )

    def set_layer(self, agent_name: str, segment_id: str, data: dict) -> None:
        if agent_name not in self._data["layers"]:
            self._data["layers"][agent_name] = {}
        self._data["layers"][agent_name][segment_id] = data
        self.save()

    def get_agent_layer(self, agent_name: str) -> dict:
        """Return the entire layer dict for an agent (segment_id → data)."""
        return self._data["layers"].get(agent_name, {})

    def get_agent_data(self, agent_name: str) -> dict:
        """Return agent-level (non-per-segment) data."""
        return self._data["agent_data"].get(agent_name, {})

    def set_agent_data(self, agent_name: str, data: dict) -> None:
        self._data["agent_data"][agent_name] = data
        self.save()

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def take_snapshot(self) -> str:
        snap_id = f"snap_{uuid.uuid4().hex[:8]}"
        self._data["snapshots"][snap_id] = {
            "sequence": list(self._data["current"]["sequence"]),  # deep copy of raw dicts
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._data["current"]["snapshot_ref"] = snap_id
        self.save()
        return snap_id

    def rollback(self, snap_id: str) -> bool:
        snap = self._data["snapshots"].get(snap_id)
        if snap is None:
            return False
        self._data["current"]["sequence"] = list(snap["sequence"])
        self._data["current"]["snapshot_ref"] = snap_id
        self.save()
        return True

    def get_snapshot(self, snap_id: str) -> dict | None:
        return self._data["snapshots"].get(snap_id)

    def list_snapshots(self) -> list[dict]:
        return [
            {"snap_id": sid, **data}
            for sid, data in self._data["snapshots"].items()
        ]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def add_history(self, prompt: str, summary: str, snapshot_ref: str = "") -> None:
        entry = {
            "prompt": prompt,
            "summary": summary,
            "snapshot_ref": snapshot_ref,
        }
        self._data["history"].append(entry)
        self.save()

    def get_history(self) -> list[dict]:
        return list(self._data["history"])

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def record_error(self, agent_name: str, message: str) -> None:
        self._data["errors"].append({
            "agent": agent_name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

    # ------------------------------------------------------------------
    # LLM context (lean)
    # ------------------------------------------------------------------

    def to_llm_context(
        self,
        agent_names: list[str] | None = None,
        agents: dict | None = None,   # {name: BaseAgent instance}
    ) -> dict:
        """
        Build a compact dict for the LLM.

        - No full transcripts (text previews capped at 150 chars).
        - No word-level token lists.
        - No embeddings.
        - Last 5 history summaries only.
        """
        source = self._data.get("source", {})
        pool = self._data["segment_pool"]
        sequence = self._data["current"]["sequence"]

        current_segments = []
        for entry in sequence:
            sid = entry["segment_id"]
            seg = pool.get(sid, {})
            preview = (seg.get("text", "") or "")[:150]
            current_segments.append({
                "id": sid,
                "duration": seg.get("duration", 0.0),
                "text_preview": preview,
            })

        history_summaries = [
            h.get("summary", "") for h in self._data["history"][-5:]
        ]

        agent_context: dict = {}
        if agents:
            names_to_include = set(agent_names) if agent_names else set(agents.keys())
            for name, agent in agents.items():
                if name in names_to_include:
                    try:
                        agent_context[name] = agent.get_lean_context()
                    except Exception:
                        agent_context[name] = {}

        return {
            "source": {
                "filename": source.get("filename", ""),
                "duration": source.get("duration", 0.0),
            },
            "segment_count": len(pool),
            "current_segments": current_segments,
            "history": history_summaries,
            "agent_context": agent_context,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def load(self) -> None:
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def to_dict(self) -> dict:
        """Return the raw internal state dict (for API responses)."""
        return self._data

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def project_dir(self) -> Path:
        return self.projects_dir / self.project_id

    @property
    def chroma_dir(self) -> Path:
        return self.project_dir / "chroma"

    @property
    def exports_dir(self) -> Path:
        return self.project_dir / "exports"

    @property
    def source_path(self) -> str:
        return self._data.get("source", {}).get("path", "")

    def segment_count(self) -> int:
        return len(self._data["segment_pool"])

    def current_sequence_length(self) -> float:
        """Total duration of segments in current.sequence."""
        pool = self._data["segment_pool"]
        total = 0.0
        for entry in self._data["current"]["sequence"]:
            sid = entry["segment_id"]
            seg = pool.get(sid, {})
            total += seg.get("duration", 0.0)
        return total
