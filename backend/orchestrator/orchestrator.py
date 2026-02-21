"""
orchestrator/orchestrator.py

The Orchestrator — receives a user prompt and drives the full agent pipeline.

9-step flow:
  1. intent_detector.scan(prompt)      — keyword scan, no LLM
  2. context_builder.build(...)         — lean context for LLM
  3. llm_client.tool_call(...)          — single LLM call; model picks tools
  4. Validate tool names vs registry    — reject unknown tools, no execution
  5. state.take_snapshot()             — pre-execution checkpoint
  6. task_graph.build(tool_calls)       — topological sort → parallel groups
  7. Execute groups with asyncio.gather — each group runs concurrently
  8. On failure → state.rollback(snap_id)
  9. state.add_history(prompt, summary)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from agents.base import ToolCall, ToolResult
from agents.registry import AgentRegistry
from llm.client import LLMClient
from llm.prompts import ORCHESTRATOR_SYSTEM
from orchestrator.intent_detector import scan
from orchestrator.context_builder import ContextAssembler
from orchestrator.task_graph import TaskGraph

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    success: bool
    prompt: str
    tool_calls: list[ToolCall]
    results: list[ToolResult]
    summary: str
    snap_id: str | None = None
    error: str | None = None


class Orchestrator:
    """
    Central prompt handler.

    Instantiated once per project in app.py:
        orchestrator = Orchestrator(registry, llm_client, state)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        llm_client: LLMClient,
        state,
    ) -> None:
        self.registry = registry
        self.llm_client = llm_client
        self.state = state

    async def handle_prompt(self, prompt: str) -> OrchestratorResult:
        """
        Handle a user prompt end-to-end.

        Returns OrchestratorResult with success/failure info.
        """
        logger.info("Orchestrator handling prompt: '%s'", prompt[:80])

        # ----------------------------------------------------------------
        # Step 1: Intent detection (keyword scan, no LLM)
        # ----------------------------------------------------------------
        agent_names = scan(prompt)
        logger.debug("Detected agent names: %s", agent_names)

        # ----------------------------------------------------------------
        # Step 2: Build lean context
        # ----------------------------------------------------------------
        # Map snake_case names (matching intent_detector output) → agent instance
        agents_by_name = {
            type(a).__name__.lower().replace("agent", "_agent"): a
            for a in self.registry.all_agents()
        }

        # Build context using agent names detected by intent scanner
        context = ContextAssembler.build(
            state=self.state,
            agent_names=agent_names,
            agents=agents_by_name,
        )

        # ----------------------------------------------------------------
        # Step 3: Single LLM tool-calling call
        # ----------------------------------------------------------------
        all_tools = self.registry.all_tools()
        if not all_tools:
            return OrchestratorResult(
                success=False,
                prompt=prompt,
                tool_calls=[],
                results=[],
                summary="No agents registered.",
                error="No tools available.",
            )

        try:
            tool_calls = await self.llm_client.tool_call(
                system=ORCHESTRATOR_SYSTEM,
                user=prompt,
                tools=all_tools,
                context=context,
            )
        except Exception as exc:
            logger.exception("LLM tool_call failed: %s", exc)
            return OrchestratorResult(
                success=False,
                prompt=prompt,
                tool_calls=[],
                results=[],
                summary=f"LLM call failed: {exc}",
                error=str(exc),
            )

        if not tool_calls:
            return OrchestratorResult(
                success=True,
                prompt=prompt,
                tool_calls=[],
                results=[],
                summary="No tool calls returned by LLM — prompt may be out of scope.",
            )

        logger.info("LLM returned %d tool call(s): %s", len(tool_calls), [c.name for c in tool_calls])

        # ----------------------------------------------------------------
        # Step 4: Validate tool names against registry
        # ----------------------------------------------------------------
        registered_names = set(self.registry.registered_tool_names())
        unknown = TaskGraph.validate_names(tool_calls, registered_names)
        if unknown:
            return OrchestratorResult(
                success=False,
                prompt=prompt,
                tool_calls=tool_calls,
                results=[],
                summary=f"Unknown tools requested: {unknown}",
                error=f"Unknown tool names: {unknown}",
            )

        # ----------------------------------------------------------------
        # Step 5: Take snapshot (pre-execution checkpoint)
        # ----------------------------------------------------------------
        snap_id = self.state.take_snapshot()
        logger.debug("Snapshot taken: %s", snap_id)

        # ----------------------------------------------------------------
        # Step 6: Build execution graph (topological sort → parallel groups)
        # ----------------------------------------------------------------
        try:
            groups = TaskGraph.build(tool_calls)
        except ValueError as exc:
            return OrchestratorResult(
                success=False,
                prompt=prompt,
                tool_calls=tool_calls,
                results=[],
                summary=f"Execution graph error: {exc}",
                snap_id=snap_id,
                error=str(exc),
            )

        # ----------------------------------------------------------------
        # Step 7: Execute groups with asyncio.gather
        # ----------------------------------------------------------------
        all_results: list[ToolResult] = []
        failed = False
        fail_error = ""

        for group_idx, group in enumerate(groups):
            logger.debug(
                "Executing group %d/%d: %s",
                group_idx + 1, len(groups), [c.name for c in group],
            )
            tasks = [self._execute_one(call) for call in group]
            group_results = await asyncio.gather(*tasks, return_exceptions=True)

            for call, result in zip(group, group_results):
                if isinstance(result, Exception):
                    result = ToolResult(success=False, data={}, error=str(result))

                all_results.append(result)

                if not result.success:
                    failed = True
                    fail_error = result.error or f"Tool {call.name} failed"
                    logger.error("Tool '%s' failed: %s", call.name, result.error)
                    break

            if failed:
                break

        # ----------------------------------------------------------------
        # Step 8: Rollback on failure
        # ----------------------------------------------------------------
        if failed:
            self.state.rollback(snap_id)
            logger.info("Rolled back to snapshot %s after failure.", snap_id)
            return OrchestratorResult(
                success=False,
                prompt=prompt,
                tool_calls=tool_calls,
                results=all_results,
                summary=f"Failed: {fail_error}. State rolled back.",
                snap_id=snap_id,
                error=fail_error,
            )

        # ----------------------------------------------------------------
        # Step 9: Record history
        # ----------------------------------------------------------------
        summary = self._build_summary(tool_calls, all_results)
        self.state.add_history(prompt, summary, snap_id)
        logger.info("Prompt handled successfully. Summary: %s", summary)

        return OrchestratorResult(
            success=True,
            prompt=prompt,
            tool_calls=tool_calls,
            results=all_results,
            summary=summary,
            snap_id=snap_id,
        )

    async def _execute_one(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call via the registry."""
        agent = self.registry.get_agent(call.name)
        if agent is None:
            return ToolResult(
                success=False,
                data={},
                error=f"No agent found for tool: {call.name}",
            )
        return await agent.execute_tool(call.name, call.params)

    def _build_summary(
        self,
        tool_calls: list[ToolCall],
        results: list[ToolResult],
    ) -> str:
        """Build a one-line summary of what was done."""
        parts = []
        for call, result in zip(tool_calls, results):
            if result.success:
                # Extract meaningful data from results
                data = result.data
                if call.name == "transcription.transcribe":
                    parts.append(f"Transcribed {data.get('segment_count', '?')} segments.")
                elif call.name == "search.find_segments":
                    ids = data.get("segment_ids", [])
                    parts.append(f"Found {len(ids)} segments for '{data.get('query', '')}'.")
                elif call.name == "edit.keep_only":
                    parts.append(f"Kept {len(data.get('kept', []))} segments.")
                elif call.name == "edit.remove_short":
                    parts.append(f"Removed {data.get('removed_count', 0)} short segments.")
                elif call.name == "edit.reorder":
                    parts.append("Reordered sequence.")
                elif call.name == "edit.set_transition":
                    parts.append(
                        f"Set {data.get('type', '')} transition on {data.get('segment_id', '')}."
                    )
                elif call.name == "edit.trim_segment":
                    parts.append(f"Trimmed segment {data.get('segment_id', '')}.")
                elif call.name == "edit.add_effect":
                    parts.append(
                        f"Added {data.get('effect_type', '')} effect to {data.get('segment_id', '')}."
                    )
                elif call.name == "export.export":
                    parts.append(
                        f"Exported {data.get('resolution', '')} at "
                        f"{data.get('file_size_mb', 0):.1f} MB."
                    )
                else:
                    parts.append(f"Executed {call.name}.")
            else:
                parts.append(f"{call.name} failed.")

        return " ".join(parts) if parts else "Done."
