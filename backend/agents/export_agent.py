"""
agents/export_agent.py

ExportAgent — compiles the timeline and runs FFmpeg.

Reads:
  current.sequence    — ordered segment IDs with transitions
  layers["edit_agent"] — per-segment trim + effects
  segment_pool        — source timecodes and file paths

Delegates to:
  media/effect_compiler.py — builds FFmpeg filter_complex
  media/ffmpeg_wrapper.py  — runs FFmpeg

Tools:
  export.export {resolution: "full"|"preview", output_name: str}
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)


class ExportAgent(BaseAgent):
    """Compiles the timeline into a video file using FFmpeg."""

    def description(self) -> str:
        return "Exports the current timeline sequence to an MP4 file."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="export.export",
                description=(
                    "Export the current timeline to an MP4 file at source resolution. "
                    "Returns the path of the exported file."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "resolution": {
                            "type": "string",
                            "enum": ["full"],
                            "description": "Output resolution (always full/source resolution)",
                        },
                        "output_name": {
                            "type": "string",
                            "description": "Output filename (without extension). Defaults to 'export'.",
                        },
                    },
                    "required": [],
                },
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("export.export", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name != "export.export":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        resolution = params.get("resolution", "full")  # Default to full resolution
        output_name = params.get("output_name", "export")

        try:
            return await self._export(resolution, output_name)
        except Exception as exc:
            logger.exception("Export failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _export(self, resolution: str, output_name: str) -> ToolResult:
        from media import effect_compiler, ffmpeg_wrapper
        from datetime import datetime

        sequence = self.state.get_current_sequence()
        if not sequence:
            return ToolResult(
                success=False,
                data={},
                error="Current sequence is empty. Nothing to export.",
            )

        # Generate default names if None or empty
        if not resolution:
            resolution = "full"
        
        if not output_name:
            # Generate timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"export_{timestamp}"

        # Log export start
        logger.info("=" * 70)
        logger.info("🚀 EXPORT STARTED")
        logger.info("  Resolution: %s", resolution)
        logger.info("  Output name: %s", output_name)
        logger.info("  Segments to export: %d", len(sequence))
        logger.info("=" * 70)

        # Log sequence details before export
        logger.info("=" * 70)
        logger.info("EXPORT: Exporting %d clips from current_sequence", len(sequence))
        logger.info("RAW SEQUENCE TYPE: %s", type(sequence))
        logger.info("RAW SEQUENCE DATA: %s", sequence)
        
        segment_pool = self.state._data["segment_pool"]
        logger.info("RAW SEGMENT_POOL TYPE: %s", type(segment_pool))
        logger.info("RAW SEGMENT_POOL KEYS: %s", list(segment_pool.keys()) if hasattr(segment_pool, 'keys') else 'N/A')
        
        for i, entry in enumerate(sequence, 1):
            logger.info("  Entry %d TYPE: %s", i, type(entry))
            logger.info("  Entry %d DATA: %s", i, entry)
            
            seg = segment_pool.get(entry.segment_id if hasattr(entry, 'segment_id') else entry.get('segment_id'))
            logger.info("  Segment TYPE: %s", type(seg))
            logger.info("  Segment DATA: %s", seg)
            
            if seg:
                # Handle both dict and object access
                if isinstance(seg, dict):
                    start = seg.get('start', 0)
                    end = seg.get('end', 0)
                    duration = seg.get('duration', 0)
                    text = seg.get('text', '')
                else:
                    start = seg.start
                    end = seg.end
                    duration = seg.duration
                    text = seg.text
                    
                logger.info(
                    "  [%d] %s: %.2fs-%.2fs (duration=%.2fs) - %s",
                    i, entry.segment_id if hasattr(entry, 'segment_id') else entry.get('segment_id'),
                    start, end, duration, text[:50] if text else ""
                )
        logger.info("=" * 70)

        self._emit("stage", {"stage": "compile", "status": "running"})
        
        logger.info("📊 COMPILING TIMELINE...")
        logger.info("  Building FFmpeg filter_complex from %d segments", len(sequence))

        # Build FFmpeg arguments from timeline state
        compiled = effect_compiler.compile(
            sequence=sequence,
            layers=self.state._data["layers"],
            segment_pool=self.state._data["segment_pool"],
        )

        logger.info("✓ COMPILATION COMPLETE")
        logger.info("  Inputs prepared: %d", len(compiled["inputs"]))
        logger.info("  Filter complex length: %d chars", len(compiled.get("filter_complex", "")))

        if not compiled["inputs"]:
            return ToolResult(
                success=False,
                data={},
                error="No valid segments found for export.",
            )

        # Ensure exports directory exists
        exports_dir = self.state.exports_dir
        exports_dir.mkdir(parents=True, exist_ok=True)

        output_path = str(exports_dir / f"{output_name}_{resolution}.mp4")
        encoder = ffmpeg_wrapper.detect_encoder()

        self._emit("stage", {
            "stage": "encode",
            "status": "running",
            "encoder": encoder,
            "segments": len(compiled["inputs"]),
        })
        
        logger.info("=" * 70)
        logger.info("🎬 STARTING FFMPEG ENCODING")
        logger.info("  Encoder: %s", encoder)
        logger.info("  Resolution: %s", resolution)
        logger.info("  Output: %s", output_path)
        logger.info("  Segments: %d", len(compiled["inputs"]))
        logger.info("=" * 70)

        ffmpeg_wrapper.export(
            inputs=compiled["inputs"],
            filter_complex=compiled["filter_complex"],
            final_video=compiled.get("final_video", ""),
            final_audio=compiled.get("final_audio", ""),
            output_path=output_path,
            encoder=encoder,
            resolution=resolution,
        )

        self._emit("stage", {"stage": "encode", "status": "done", "output": output_path})
        
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        
        logger.info("=" * 70)
        logger.info("✅ EXPORT COMPLETE!")
        logger.info("  Output: %s", output_path)
        logger.info("  File size: %.2f MB", file_size / (1024 * 1024))
        logger.info("  Segments: %d", len(compiled["inputs"]))
        logger.info("=" * 70)
        
        return ToolResult(
            success=True,
            data={
                "output_path": output_path,
                "resolution": resolution,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "segment_count": len(compiled["inputs"]),
            },
        )

    def get_lean_context(self) -> dict:
        data = self.state.get_agent_data("export_agent")
        return {
            "last_export": data.get("last_export", ""),
            "resolution": data.get("resolution", ""),
        }
