"""
agents/registry.py

AgentRegistry — maps tool_name → agent instance.

Usage in app.py:
    registry = AgentRegistry()
    registry.register(TranscriptionAgent(state, config))
    registry.register(SearchAgent(state, config))
    ...
    orchestrator = Orchestrator(registry, llm_client, state)

The registry collects all Tool declarations from every registered agent via
get_tools() and exposes them as a single flat list via all_tools().
"""

from __future__ import annotations

from agents.base import BaseAgent, Tool


class AgentRegistry:
    """
    Single source of truth for which agents and tools are active.

    Invariant: every tool_name maps to exactly one agent.
    Duplicate tool names across agents will raise ValueError at registration.
    """

    def __init__(self) -> None:
        self._tool_map: dict[str, BaseAgent] = {}   # tool_name → agent
        self._agents: list[BaseAgent] = []

    def register(self, agent: BaseAgent) -> None:
        """
        Register an agent and index all its tools.

        Raises ValueError if a tool name is already claimed by another agent.
        """
        for tool in agent.get_tools():
            if tool.name in self._tool_map:
                existing = self._tool_map[tool.name]
                raise ValueError(
                    f"Tool '{tool.name}' already registered by "
                    f"{type(existing).__name__}. Cannot re-register from "
                    f"{type(agent).__name__}."
                )
            self._tool_map[tool.name] = agent
        self._agents.append(agent)

    def get_agent(self, tool_name: str) -> BaseAgent | None:
        """Return the agent that owns tool_name, or None."""
        return self._tool_map.get(tool_name)

    def all_tools(self) -> list[Tool]:
        """Flat list of all registered tools — passed to the LLM."""
        tools: list[Tool] = []
        seen: set[str] = set()
        for agent in self._agents:
            for tool in agent.get_tools():
                if tool.name not in seen:
                    tools.append(tool)
                    seen.add(tool.name)
        return tools

    def all_agents(self) -> list[BaseAgent]:
        return list(self._agents)

    def agents_by_name(self) -> dict[str, BaseAgent]:
        """Map agent class name → agent instance."""
        return {type(a).__name__: a for a in self._agents}

    def registered_tool_names(self) -> list[str]:
        return list(self._tool_map.keys())

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tool_map
