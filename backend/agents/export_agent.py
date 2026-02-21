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
                    "Export the current timeline to an MP4 file. "
                    "resolution='preview' exports at 720p (fast); "
                    "resolution='full' exports at source resolution. "
                    "Returns the path of the exported file."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "resolution": {
                            "type": "string",
                            "enum": ["full", "preview"],
                            "description": "Output resolution (default: preview)",
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

        resolution = params.get("resolution", "preview")
        output_name = params.get("output_name", "export")

        try:
            return await self._export(resolution, output_name)
        except Exception as exc:
            logger.exception("Export failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _export(self, resolution: str, output_name: str) -> ToolResult:
        from media import effect_compiler, ffmpeg_wrapper

        sequence = self.state.get_current_sequence()
        if not sequence:
            return ToolResult(
                success=False,
                data={},
                error="Current sequence is empty. Nothing to export.",
            )

        self._emit("stage", {"stage": "compile", "status": "running"})

        # Build FFmpeg arguments from timeline state
        compiled = effect_compiler.compile(
            sequence=sequence,
            layers=self.state._data["layers"],
            segment_pool=self.state._data["segment_pool"],
        )

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
        logger.info(
            "Exporting %d segments @ %s using %s → %s",
            len(compiled["inputs"]), resolution, encoder, output_path,
        )

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
        logger.info("Export complete: %s", output_path)

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
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
