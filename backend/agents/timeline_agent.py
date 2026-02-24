"""
agents/timeline_agent.py

TimelineAgent — provides tools for querying timeline state.

Allows the ReAct agent to inspect the timeline, segments, history,
and snapshots without modifying them.

Tools:
  timeline.get_segments       {}
  timeline.get_sequence       {}
  timeline.get_effective_segments {}
  timeline.get_history        {}
  timeline.list_snapshots     {}
  timeline.get_source_info    {}
  timeline.rollback           {snap_id: str}
  timeline.take_snapshot      {}
"""

from __future__ import annotations

import logging
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)


class TimelineAgent(BaseAgent):
    """
    Provides read-only access to timeline state for the ReAct agent.
    
    Enables the agent to query current segments, sequence, history,
    and snapshots to make informed decisions.
    """

    def description(self) -> str:
        return "Query timeline state: segments, sequence, history, and snapshots."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="timeline_get_segments",
                description=(
                    "Get all segments in the timeline pool. "
                    "Returns list of segments with id, text, duration, start, end."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_get_sequence",
                description=(
                    "Get the current editing sequence. "
                    "Returns ordered list of segment IDs that will be exported."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_get_effective_segments",
                description=(
                    "Get virtual timeline with edits applied. "
                    "Shows segments as they will appear in export (with trim/effects)."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_get_history",
                description=(
                    "Get conversation history. "
                    "Returns recent prompts and summaries."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_list_snapshots",
                description=(
                    "List all saved snapshots. "
                    "Returns snapshot IDs and timestamps."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_get_source_info",
                description=(
                    "Get source video information. "
                    "Returns filename, duration, and path."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="timeline_rollback",
                description=(
                    "Restore timeline to a previous snapshot. "
                    "Use timeline.list_snapshots first to get snapshot IDs."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "snap_id": {
                            "type": "string",
                            "description": "Snapshot ID to restore (e.g., 'snap_abc123')",
                        }
                    },
                    "required": ["snap_id"],
                },
            ),
            Tool(
                name="timeline_take_snapshot",
                description=(
                    "Save current timeline state as a snapshot. "
                    "Returns the new snapshot ID."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    async def run(self, params: dict) -> AgentStatus:
        # TimelineAgent is always called via execute_tool
        return AgentStatus.SUCCESS

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        dispatch = {
            "timeline_get_segments": self._get_segments,
            "timeline_get_sequence": self._get_sequence,
            "timeline_get_effective_segments": self._get_effective_segments,
            "timeline_get_history": self._get_history,
            "timeline_list_snapshots": self._list_snapshots,
            "timeline_get_source_info": self._get_source_info,
            "timeline_rollback": self._rollback,
            "timeline_take_snapshot": self._take_snapshot,
        }
        
        handler = dispatch.get(name)
        if handler is None:
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        try:
            return await handler(params)
        except Exception as exc:
            logger.exception("TimelineAgent tool '%s' failed: %s", name, exc)
            return ToolResult(success=False, data={}, error=str(exc))

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _get_segments(self, params: dict) -> ToolResult:
        """Get all segments from pool."""
        segments = self.state.get_all_segments()
        
        # Convert to simple dict for LLM
        segment_list = []
        for seg_id, seg in segments.items():
            segment_list.append({
                "id": seg.id,
                "text": seg.text[:150],  # Truncate for LLM context
                "duration": round(seg.duration, 2),
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
            })
        
        # Sort by start time
        segment_list.sort(key=lambda s: s["start"])
        
        return ToolResult(
            success=True,
            data={
                "segments": segment_list,
                "count": len(segment_list),
            },
        )

    async def _get_sequence(self, params: dict) -> ToolResult:
        """Get current editing sequence."""
        sequence = self.state.get_current_sequence()
        pool = self.state.get_all_segments()
        
        sequence_data = []
        for entry in sequence:
            seg = pool.get(entry.segment_id)
            if seg:
                sequence_data.append({
                    "segment_id": entry.segment_id,
                    "text": seg.text[:100],
                    "duration": round(seg.duration, 2),
                    "has_transition": entry.transition_in is not None,
                })
        
        return ToolResult(
            success=True,
            data={
                "sequence": sequence_data,
                "length": len(sequence_data),
                "total_duration": round(self.state.current_sequence_length(), 2),
            },
        )

    async def _get_effective_segments(self, params: dict) -> ToolResult:
        """Get virtual timeline with edits applied."""
        sequence = self.state.get_current_sequence()
        
        effective_segments = []
        for entry in sequence:
            seg = self.state.get_effective_segment(entry.segment_id)
            if seg:
                # Get edit layer to show what edits are applied
                edit_layer = self.state.get_layer("edit_agent", entry.segment_id)
                
                effective_segments.append({
                    "id": seg.id,
                    "text": seg.text[:100],
                    "original_duration": round(seg.duration, 2),
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "trimmed": edit_layer.get("trim") is not None if edit_layer else False,
                    "effects_count": len(edit_layer.get("effects", [])) if edit_layer else 0,
                })
        
        return ToolResult(
            success=True,
            data={
                "effective_segments": effective_segments,
                "count": len(effective_segments),
            },
        )

    async def _get_history(self, params: dict) -> ToolResult:
        """Get conversation history."""
        history = self.state.get_history()
        
        # Return last 10 entries
        recent_history = history[-10:]
        
        history_data = []
        for entry in recent_history:
            history_data.append({
                "prompt": entry.get("prompt", "")[:150],
                "summary": entry.get("summary", "")[:150],
            })
        
        return ToolResult(
            success=True,
            data={
                "history": history_data,
                "count": len(history_data),
                "total_count": len(history),
            },
        )

    async def _list_snapshots(self, params: dict) -> ToolResult:
        """List all snapshots."""
        snapshots = self.state.list_snapshots()
        
        return ToolResult(
            success=True,
            data={
                "snapshots": snapshots,
                "count": len(snapshots),
            },
        )

    async def _get_source_info(self, params: dict) -> ToolResult:
        """Get source video information."""
        source = self.state.get_source()
        
        return ToolResult(
            success=True,
            data={
                "filename": source.get("filename", ""),
                "duration": round(source.get("duration", 0.0), 2),
                "path": source.get("path", ""),
            },
        )

    async def _rollback(self, params: dict) -> ToolResult:
        """Rollback to a snapshot."""
        snap_id = params.get("snap_id")
        
        if not snap_id:
            return ToolResult(success=False, data={}, error="snap_id is required")
        
        success = self.state.rollback(snap_id)
        
        if not success:
            return ToolResult(
                success=False,
                data={},
                error=f"Snapshot {snap_id} not found",
            )
        
        return ToolResult(
            success=True,
            data={"snap_id": snap_id, "message": f"Restored to snapshot {snap_id}"},
        )

    async def _take_snapshot(self, params: dict) -> ToolResult:
        """Take a new snapshot."""
        snap_id = self.state.take_snapshot()
        
        return ToolResult(
            success=True,
            data={"snap_id": snap_id, "message": f"Created snapshot {snap_id}"},
        )

    # ------------------------------------------------------------------
    # Agent context
    # ------------------------------------------------------------------

    def get_lean_context(self) -> dict:
        return {
            "segment_count": self.state.segment_count(),
            "sequence_length": len(self.state.get_current_sequence()),
            "snapshot_count": len(self.state.list_snapshots()),
        }
