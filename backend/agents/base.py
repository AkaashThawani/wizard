"""
agents/base.py

Base contracts for all Wizard agents.

Design:
- Tool: declares a callable operation to the LLM (name, description, JSON-schema params)
- ToolResult: returned by execute_tool()
- BaseAgent: abstract base every agent inherits
- Agents declare their tools via get_tools(); the orchestrator collects all tools
  from all registered agents and passes them to the LLM in a single call.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """
    A callable operation declared by an agent.

    The LLM reads `name` and `description` to decide when to call this tool.
    `parameters` is a JSON Schema dict (type, properties, required).
    `depends_on` lists tool names that must execute before this one.
    """
    name: str
    description: str
    parameters: dict
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""
    name: str
    params: dict
    depends_on: list[str] = field(default_factory=list)
    call_id: str = ""  # populated by LLM client (provider-specific id)


@dataclass
class ToolResult:
    """Returned by execute_tool()."""
    success: bool
    data: dict
    error: str | None = None


class AgentStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"


# Progress callback type: (event: str, data: dict) -> None
ProgressCallback = Callable[[str, dict], None]


# ---------------------------------------------------------------------------
# Abstract base agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """
    All Wizard agents inherit from this class.

    Lifecycle:
      1. Instantiated with (state, config) in app.py.
      2. Registered via AgentRegistry.register(agent) — calls get_tools().
      3. Orchestrator collects all_tools() → passes to LLM.
      4. LLM returns ToolCall list → orchestrator calls execute_tool() per call.
    """

    def __init__(
        self,
        state: Any,   # TimelineState — using Any to avoid circular imports
        config: dict,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.state = state
        self.config = config
        self._progress_callback = progress_callback

    def set_progress_callback(self, cb: ProgressCallback) -> None:
        self._progress_callback = cb

    def _emit(self, event: str, data: dict | None = None) -> None:
        """Emit a progress event if a callback is registered."""
        if self._progress_callback is not None:
            try:
                self._progress_callback(event, data or {})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Abstract interface — every agent must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self, params: dict) -> AgentStatus:
        """
        Pipeline entry point — used for batch/pipeline operations
        (e.g. TranscriptionAgent runs the full pipeline here).
        """

    @abstractmethod
    def get_tools(self) -> list[Tool]:
        """
        Returns all tools this agent can execute.
        Called once at registration time; results are cached in AgentRegistry.
        """

    @abstractmethod
    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        """
        Dispatches a single named tool call.
        Called by the orchestrator after the LLM selects a tool.
        """

    @abstractmethod
    def get_lean_context(self) -> dict:
        """
        Returns a compact dict summarising this agent's current state.
        Included in the LLM context (to_llm_context).
        Keep small — the LLM reads this every prompt.
        """

    @abstractmethod
    def description(self) -> str:
        """One-line description of this agent's capabilities."""

    # ------------------------------------------------------------------
    # Concrete helpers (do not override)
    # ------------------------------------------------------------------

    def can_handle(self, tool_name: str) -> bool:
        """True if this agent owns the named tool."""
        return any(t.name == tool_name for t in self.get_tools())

    def tool_names(self) -> list[str]:
        return [t.name for t in self.get_tools()]
