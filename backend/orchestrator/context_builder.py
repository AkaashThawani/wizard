"""
orchestrator/context_builder.py

Assembles the lean context dict that is passed to the LLM tool_call().

Keeps the context small:
- No full transcripts
- No word-level token lists
- No embedding vectors
- Only the last 5 history summaries
- Only lean_context from agents that are likely relevant (intent-filtered)
"""

from __future__ import annotations

import json


class ContextAssembler:
    """
    Builds the LLM context dict from TimelineState and agent lean contexts.
    """

    @staticmethod
    def build(
        state,
        agent_names: set[str] | None = None,
        agents: dict | None = None,
    ) -> dict:
        """
        Build context dict for the LLM.

        Args:
            state: TimelineState instance.
            agent_names: Set of agent names to include (from intent_detector.scan()).
                         If None, includes all agents.
            agents: Dict of {agent_name: BaseAgent instance} for lean_context calls.
                    If None, no agent_context is included.

        Returns:
            Compact dict ready to be serialised and injected into the LLM prompt.
        """
        return state.to_llm_context(
            agent_names=list(agent_names) if agent_names else None,
            agents=agents,
        )

    @staticmethod
    def format_for_system(context: dict) -> str:
        """
        Format the context dict as a readable string for injection into
        the LLM system prompt or user message.
        """
        return json.dumps(context, indent=2, ensure_ascii=False)
