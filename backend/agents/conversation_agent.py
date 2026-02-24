"""
agents/conversation_agent.py

ConversationAgent — handles casual chat and non-action messages.

When the user sends casual messages like "hi", "thanks", "how are you",
the LLM should call conversation.talk_user instead of failing with no tool calls.

This ensures the LLM ALWAYS calls at least one tool for every user message.

Tools:
  conversation.talk_user {message: str}
"""

from __future__ import annotations

import logging
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)


class ConversationAgent(BaseAgent):
    """Handles conversational responses when user is chatting, not requesting actions."""

    def description(self) -> str:
        return "Provides conversational responses to casual user messages."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="conversation_talk_user",
                description=(
                    "Respond conversationally to the user. "
                    "Use this when the user is greeting you, thanking you, "
                    "asking how you are, or making casual conversation. "
                    "DO NOT use this for action requests - use the appropriate action tools instead."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Your conversational response to the user",
                        },
                    },
                    "required": ["message"],
                },
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("conversation_talk_user", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name != "conversation_talk_user":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        message = params.get("message", "").strip()
        
        if not message:
            return ToolResult(success=False, data={}, error="message is required")

        # Just return the message - no state modification needed
        logger.info("Conversational response: %s", message[:100])
        
        return ToolResult(
            success=True,
            data={"message": message},
        )

    def get_lean_context(self) -> dict:
        return {}
