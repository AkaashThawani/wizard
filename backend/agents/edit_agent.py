"""
agents/edit_agent.py

EditAgent — pure Python, no ML, no LLM.

All mutations are non-destructive: they write to state.layers["edit_agent"]
or update current.sequence. Nothing touches the source file.

Tools:
  edit.keep_only      {segment_ids: list[str]}
  edit.remove_short   {min_duration_s: float}
  edit.reorder        {segment_ids: list[str]}
  edit.set_transition {segment_id: str, type: str, duration_s: float}
  edit.trim_segment   {segment_id: str, start_offset: float, end_offset: float}
  edit.add_effect     {segment_id: str, effect_type: str, params: dict}
"""

from __future__ import annotations

import logging
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus
from timeline.models import SequenceEntry, Transition, Effect, edit_layer_to_dict, edit_layer_from_dict, EditLayer
from timeline.schema import EffectType, TransitionType

logger = logging.getLogger(__name__)


class EditAgent(BaseAgent):
    """
    Edits the current sequence and applies non-destructive effects.

    Pure Python — fast, deterministic, no external calls.
    """

    def description(self) -> str:
        return "Edits the timeline: filter, reorder, trim, transitions, and effects."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="edit.keep_only",
                description=(
                    "Replace the current sequence with only the specified segments. "
                    "All other segments remain in the pool but are excluded from the edit. "
                    "Use after search.find_segments to build a focused cut."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ordered list of segment IDs to keep in the sequence",
                        }
                    },
                    "required": ["segment_ids"],
                },
                depends_on=["search.find_segments"],
            ),
            Tool(
                name="edit.remove_short",
                description=(
                    "Remove all segments from the current sequence whose duration "
                    "is less than min_duration_s seconds."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "min_duration_s": {
                            "type": "number",
                            "description": "Minimum segment duration in seconds",
                        }
                    },
                    "required": ["min_duration_s"],
                },
            ),
            Tool(
                name="edit.reorder",
                description=(
                    "Reorder the current sequence to match the given segment ID order. "
                    "All specified IDs must already be in the current sequence."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New ordered list of segment IDs",
                        }
                    },
                    "required": ["segment_ids"],
                },
            ),
            Tool(
                name="edit.set_transition",
                description=(
                    "Set the transition that plays before a segment. "
                    "type must be one of: cut, crossfade, dissolve."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_id": {
                            "type": "string",
                            "description": "ID of the segment to set transition_in for",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["cut", "crossfade", "dissolve"],
                            "description": "Transition type",
                        },
                        "duration_s": {
                            "type": "number",
                            "description": "Transition duration in seconds (default 0.5)",
                        },
                    },
                    "required": ["segment_id", "type"],
                },
            ),
            Tool(
                name="edit.trim_segment",
                description=(
                    "Trim the start or end of a segment. "
                    "start_offset: seconds to cut from the beginning. "
                    "end_offset: seconds to cut from the end. "
                    "Trim snaps to the nearest WordToken boundary (prefers confidence > 0.8)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "start_offset": {
                            "type": "number",
                            "description": "Seconds to remove from the start (default 0)",
                        },
                        "end_offset": {
                            "type": "number",
                            "description": "Seconds to remove from the end (default 0)",
                        },
                    },
                    "required": ["segment_id"],
                },
            ),
            Tool(
                name="edit.add_effect",
                description=(
                    "Add a non-destructive effect to a segment. "
                    "effect_type: volume | fade_in | fade_out | mute | caption | speed | crop. "
                    "params depends on effect_type (e.g. {level: 0.8} for volume)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "effect_type": {
                            "type": "string",
                            "enum": ["volume", "fade_in", "fade_out", "mute", "caption", "speed", "crop"],
                        },
                        "params": {
                            "type": "object",
                            "description": "Effect parameters (varies by type)",
                        },
                    },
                    "required": ["segment_id", "effect_type"],
                },
            ),
        ]

    async def run(self, params: dict) -> AgentStatus:
        # EditAgent is always called via execute_tool by the orchestrator
        return AgentStatus.SUCCESS

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        dispatch = {
            "edit.keep_only": self._keep_only,
            "edit.remove_short": self._remove_short,
            "edit.reorder": self._reorder,
            "edit.set_transition": self._set_transition,
            "edit.trim_segment": self._trim_segment,
            "edit.add_effect": self._add_effect,
        }
        handler = dispatch.get(name)
        if handler is None:
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        try:
            return await handler(params)
        except Exception as exc:
            logger.exception("EditAgent tool '%s' failed: %s", name, exc)
            return ToolResult(success=False, data={}, error=str(exc))

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _keep_only(self, params: dict) -> ToolResult:
        segment_ids = params.get("segment_ids", [])
        if not segment_ids:
            return ToolResult(success=False, data={}, error="segment_ids is required")

        pool = self.state.get_all_segments()
        current = self.state.get_current_sequence()
        current_ids = {e.segment_id for e in current}

        valid_ids = [sid for sid in segment_ids if sid in pool]
        if not valid_ids:
            return ToolResult(success=False, data={}, error="None of the provided segment IDs exist in the pool")

        # Preserve existing transitions for segments that stay
        transition_map = {e.segment_id: e.transition_in for e in current}
        new_sequence = [
            SequenceEntry(
                segment_id=sid,
                transition_in=transition_map.get(sid),
            )
            for sid in valid_ids
        ]
        self.state.set_sequence(new_sequence)

        self._update_last_op("keep_only")
        self._emit("mutation", {"op": "keep_only", "count": len(valid_ids)})
        return ToolResult(
            success=True,
            data={"kept": valid_ids, "removed_count": len(current_ids) - len(valid_ids)},
        )

    async def _remove_short(self, params: dict) -> ToolResult:
        min_dur = float(params.get("min_duration_s", 0.0))
        if min_dur <= 0:
            return ToolResult(success=False, data={}, error="min_duration_s must be positive")

        pool = self.state.get_all_segments()
        current = self.state.get_current_sequence()

        kept = []
        removed = []
        for entry in current:
            seg = pool.get(entry.segment_id)
            if seg and seg.duration >= min_dur:
                kept.append(entry)
            else:
                removed.append(entry.segment_id)

        self.state.set_sequence(kept)
        self._update_last_op("remove_short")
        self._emit("mutation", {"op": "remove_short", "removed": len(removed)})
        return ToolResult(
            success=True,
            data={"removed_count": len(removed), "remaining_count": len(kept)},
        )

    async def _reorder(self, params: dict) -> ToolResult:
        segment_ids = params.get("segment_ids", [])
        if not segment_ids:
            return ToolResult(success=False, data={}, error="segment_ids is required")

        current = self.state.get_current_sequence()
        current_map = {e.segment_id: e for e in current}
        pool = self.state.get_all_segments()

        new_sequence = []
        for sid in segment_ids:
            if sid in current_map:
                new_sequence.append(current_map[sid])
            elif sid in pool:
                new_sequence.append(SequenceEntry(segment_id=sid, transition_in=None))
            else:
                logger.warning("Reorder: segment %s not found — skipping", sid)

        self.state.set_sequence(new_sequence)
        self._update_last_op("reorder")
        return ToolResult(
            success=True,
            data={"new_order": [e.segment_id for e in new_sequence]},
        )

    async def _set_transition(self, params: dict) -> ToolResult:
        segment_id = params.get("segment_id")
        transition_type = params.get("type", "cut")
        duration_s = float(params.get("duration_s") or 0.5)

        if not segment_id:
            return ToolResult(success=False, data={}, error="segment_id is required")

        try:
            t_type = TransitionType(transition_type)
        except ValueError:
            return ToolResult(
                success=False, data={},
                error=f"Invalid transition type: {transition_type}. Use cut, crossfade, or dissolve."
            )

        current = self.state.get_current_sequence()
        updated = False
        new_sequence = []
        for entry in current:
            if entry.segment_id == segment_id:
                if t_type == TransitionType.CUT:
                    new_entry = SequenceEntry(segment_id=segment_id, transition_in=None)
                else:
                    new_entry = SequenceEntry(
                        segment_id=segment_id,
                        transition_in=Transition(type=t_type, duration_s=duration_s),
                    )
                new_sequence.append(new_entry)
                updated = True
            else:
                new_sequence.append(entry)

        if not updated:
            return ToolResult(
                success=False, data={},
                error=f"Segment {segment_id} not found in current sequence",
            )

        self.state.set_sequence(new_sequence)
        self._update_last_op("set_transition")
        return ToolResult(
            success=True,
            data={"segment_id": segment_id, "type": transition_type, "duration_s": duration_s},
        )

    async def _trim_segment(self, params: dict) -> ToolResult:
        segment_id = params.get("segment_id")
        start_offset = float(params.get("start_offset", 0.0))
        end_offset = float(params.get("end_offset", 0.0))

        if not segment_id:
            return ToolResult(success=False, data={}, error="segment_id is required")

        seg = self.state.get_effective_segment(segment_id)
        if seg is None:
            return ToolResult(success=False, data={}, error=f"Segment {segment_id} not found")

        # Snap to WordToken boundaries
        from pipeline.chunker import find_word_boundary
        snapped_start = find_word_boundary(seg, start_offset) if start_offset != 0.0 else 0.0
        snapped_end = find_word_boundary(seg, seg.duration - end_offset) if end_offset != 0.0 else 0.0

        # Read existing layer data or create new
        raw_layer = self.state.get_layer("edit_agent", segment_id)
        if raw_layer:
            layer = edit_layer_from_dict(raw_layer)
        else:
            layer = EditLayer()

        layer.trim_start = snapped_start if start_offset != 0.0 else None
        layer.trim_end = (seg.duration - snapped_end) if end_offset != 0.0 else None

        self.state.set_layer("edit_agent", segment_id, edit_layer_to_dict(layer))
        self._update_last_op("trim_segment")
        return ToolResult(
            success=True,
            data={
                "segment_id": segment_id,
                "trim_start": layer.trim_start,
                "trim_end": layer.trim_end,
            },
        )

    async def _add_effect(self, params: dict) -> ToolResult:
        segment_id = params.get("segment_id")
        effect_type_str = params.get("effect_type")
        effect_params = params.get("params", {})

        if not segment_id:
            return ToolResult(success=False, data={}, error="segment_id is required")
        if not effect_type_str:
            return ToolResult(success=False, data={}, error="effect_type is required")

        try:
            effect_type = EffectType(effect_type_str)
        except ValueError:
            return ToolResult(
                success=False, data={},
                error=f"Invalid effect_type: {effect_type_str}",
            )

        raw_layer = self.state.get_layer("edit_agent", segment_id)
        if raw_layer:
            layer = edit_layer_from_dict(raw_layer)
        else:
            layer = EditLayer()

        # Replace existing effect of same type or append
        layer.effects = [e for e in layer.effects if e.type != effect_type]
        layer.effects.append(Effect(type=effect_type, params=effect_params, enabled=True))

        self.state.set_layer("edit_agent", segment_id, edit_layer_to_dict(layer))
        self._update_last_op("add_effect")
        return ToolResult(
            success=True,
            data={"segment_id": segment_id, "effect_type": effect_type_str},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_last_op(self, op: str) -> None:
        current = self.state.get_current_sequence()
        total_duration = self.state.current_sequence_length()
        self.state.set_agent_data("edit_agent", {
            "last_op": op,
            "segment_count": len(current),
            "cut_length_s": round(total_duration, 2),
        })

    def get_lean_context(self) -> dict:
        data = self.state.get_agent_data("edit_agent")
        return {
            "last_op": data.get("last_op", ""),
            "segment_count": data.get("segment_count", 0),
            "cut_length_s": data.get("cut_length_s", 0.0),
        }
