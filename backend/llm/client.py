"""
llm/client.py

Provider-agnostic LLM wrapper.

Supports Anthropic, OpenAI, and Google Gemini. Switch provider via config.json:
    {"llm": {"provider": "anthropic", "model": "claude-sonnet-4-6"}}
    {"llm": {"provider": "openai",    "model": "gpt-4o"}}
    {"llm": {"provider": "gemini",    "model": "gemini-2.0-flash-exp"}}

Zero code changes needed to swap providers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agents.base import Tool, ToolCall

# Module-level logger (so it picks up the configuration from app.py)
logger = logging.getLogger(__name__)


class LLMClient:
    """
    Provider-agnostic wrapper around LLM APIs.

    All agent and orchestrator code calls tool_call() or complete().
    Provider-specific formatting is handled in the _to_*_tools() adapters.
    """

    def __init__(
        self,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
        
        logger.info("=" * 70)
        logger.info("🔧 LLM CLIENT INITIALIZED:")
        logger.info("  Provider: %s", self.provider)
        logger.info("  Model: %s", self.model)
        logger.info("  API Key present: %s", bool(self.api_key))
        logger.info("  Logger name: %s", logger.name)
        logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def tool_call(
        self,
        system: str,
        user: str,
        tools: list[Tool],
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> list[ToolCall]:
        """
        Make a single LLM call that returns tool invocations.

        The model reads the system prompt, user message, available tools, and conversation history,
        then returns a list of ToolCall objects (name + params).
        
        Args:
            system: System prompt
            user: Current user message
            tools: Available tools
            context: Timeline context (current_sequence, segment_count, etc.)
            history: Conversation history [{"role": "user"|"assistant", "content": "..."}]
        """
        # Add context to user message
        if context:
            user = user + "\n\n<context>\n" + json.dumps(context, indent=2) + "\n</context>"
        
        # Add conversation history to user message for context
        if history and len(history) > 0:
            history_text = "\n\n<conversation_history>\n"
            for msg in history[-6:]:  # Last 3 exchanges (6 messages)
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_text += f"{role.capitalize()}: {content}\n"
            history_text += "</conversation_history>"
            user = history_text + "\n\n" + user

        if self.provider == "anthropic":
            return await self._anthropic_tool_call(system, user, tools)
        elif self.provider == "openai":
            return await self._openai_tool_call(system, user, tools)
        elif self.provider == "gemini":
            return await self._gemini_tool_call(system, user, tools)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def complete(
        self,
        system: str,
        user: str,
        context: dict | None = None,
    ) -> str:
        """
        Make a single LLM call that returns plain text.

        Used by enricher.py and hybrid search refinement.
        """
        if context:
            user = user + "\n\n<context>\n" + json.dumps(context, indent=2) + "\n</context>"

        if self.provider == "anthropic":
            return await self._anthropic_complete(system, user)
        elif self.provider == "openai":
            return await self._openai_complete(system, user)
        elif self.provider == "gemini":
            return await self._gemini_complete(system, user)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    # ------------------------------------------------------------------
    # Anthropic adapter
    # ------------------------------------------------------------------

    async def _anthropic_tool_call(
        self, system: str, user: str, tools: list[Tool]
    ) -> list[ToolCall]:
        logger.info("🔥 _anthropic_tool_call START - function entered")
        logger.info("  Received %d tools", len(tools))
        
        import anthropic
        
        logger.info("🔥 Creating Anthropic client...")
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        
        logger.info("🔥 Converting tools to Anthropic format...")
        anthropic_tools = self._to_anthropic_tools(tools)
        logger.info("🔥 Converted to %d Anthropic tools", len(anthropic_tools))

        # LOG REQUEST
        logger.info("=" * 70)
        logger.info("🤖 ANTHROPIC LLM REQUEST:")
        logger.info("  Model: %s", self.model)
        logger.info("  Tools count: %d", len(anthropic_tools))
        logger.info("  Tool names: %s", [t["name"] for t in anthropic_tools])
        logger.info("  Tool choice: any (forced)")
        logger.info("  System prompt length: %d chars", len(system))
        logger.info("  User prompt: %s", user[:200])
        logger.info("=" * 70)

        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=anthropic_tools,
            messages=[{"role": "user", "content": user}],
            tool_choice={"type": "any"},  # Force at least one tool call
        )

        # LOG RESPONSE
        logger.info("=" * 70)
        logger.info("🤖 ANTHROPIC LLM RESPONSE:")
        logger.info("  Response content blocks: %d", len(response.content))
        for i, block in enumerate(response.content):
            logger.info("  Block %d type: %s", i, block.type)
            if block.type == "tool_use":
                logger.info("    Tool name: %s", block.name)
                logger.info("    Tool params: %s", block.input)
            elif block.type == "text":
                logger.info("    Text content: %s", block.text[:200])
        logger.info("  Stop reason: %s", response.stop_reason)
        logger.info("  Usage: input=%d, output=%d", response.usage.input_tokens, response.usage.output_tokens)
        logger.info("=" * 70)

        results: list[ToolCall] = []
        for block in response.content:
            if block.type == "tool_use":
                params = block.input if isinstance(block.input, dict) else {}
                # Extract depends_on if the model embedded it
                depends_on = params.pop("depends_on", [])
                if isinstance(depends_on, str):
                    depends_on = [depends_on]
                results.append(ToolCall(
                    name=block.name,
                    params=params,
                    depends_on=depends_on,
                    call_id=block.id,
                ))
        return results

    async def _anthropic_complete(self, system: str, user: str) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text if response.content else ""

    def _to_anthropic_tools(self, tools: list[Tool]) -> list[dict]:
        """Convert Tool list to Anthropic tool format."""
        result = []
        for t in tools:
            schema = dict(t.parameters)
            # Anthropic expects input_schema at top level
            result.append({
                "name": t.name,
                "description": t.description,
                "input_schema": schema,
            })
        return result

    # ------------------------------------------------------------------
    # OpenAI adapter
    # ------------------------------------------------------------------

    async def _openai_tool_call(
        self, system: str, user: str, tools: list[Tool]
    ) -> list[ToolCall]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        openai_tools = self._to_openai_tools(tools)

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=openai_tools,
            tool_choice="required",  # Force at least one tool call
        )

        results: list[ToolCall] = []
        msg = response.choices[0].message
        for tc in (msg.tool_calls or []):
            params = json.loads(tc.function.arguments)
            depends_on = params.pop("depends_on", [])
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            results.append(ToolCall(
                name=tc.function.name,
                params=params,
                depends_on=depends_on,
                call_id=tc.id,
            ))
        return results

    async def _openai_complete(self, system: str, user: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _to_openai_tools(self, tools: list[Tool]) -> list[dict]:
        """Convert Tool list to OpenAI tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    # ------------------------------------------------------------------
    # Gemini adapter
    # ------------------------------------------------------------------

    async def _gemini_tool_call(
        self, system: str, user: str, tools: list[Tool]
    ) -> list[ToolCall]:
        logger.info("🔥 _gemini_tool_call START - function entered")
        logger.info("  Received %d tools", len(tools))
        
        import google.generativeai as genai
        
        logger.info("🔥 Configuring Gemini API...")
        genai.configure(api_key=self.api_key)
        
        # 1. Setup Tool Config to FORCE a tool call
        # This prevents the model from returning 0 parts/plain text
        tool_config = {
            "function_calling_config": {
                "mode": "ANY",  # Forces the model to pick at least one tool
            }
        }
        
        # 2. Setup Generation Config (simple - no thinking in old SDK)
        generation_config = genai.GenerationConfig(
            max_output_tokens=8192,
            temperature=0.3,
        )
        
        # 3. Disable Safety Filters
        # "Parts: 0" usually means a safety block (e.g., "balls" keyword)
        safety_settings = [
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        logger.info("🔥 Creating Gemini model...")
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
        )
        
        logger.info("🔥 Converting tools to Gemini format...")
        gemini_tools = self._to_gemini_tools(tools)
        logger.info("🔥 Converted to %d Gemini tool declarations", len(gemini_tools))
        
        # LOG REQUEST
        logger.info("=" * 70)
        logger.info("🤖 GEMINI LLM REQUEST:")
        logger.info("  Model: %s", self.model)
        logger.info("  Tools count: %d", len(tools))
        logger.info("  Tool names: %s", [t.name for t in tools])
        logger.info("  System prompt length: %d chars", len(system))
        logger.info("  User prompt: %s", user[:200])
        logger.info("  Tool config: function_calling_config.mode = ANY (forced)")
        logger.info("  Safety filters: DISABLED (all categories)")
        logger.info("=" * 70)
        
        # Gemini expects a combined prompt (system is set in GenerativeModel)
        logger.info("🔥 Calling Gemini API...")
        response = await model.generate_content_async(
            user,
            tools=gemini_tools,
            tool_config=tool_config,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        
        # DEBUG: If response is blocked, find out why
        if not response.candidates or not response.candidates[0].content.parts:
            logger.error("=" * 70)
            logger.error("❌ GEMINI RETURNED NO PARTS")
            if response.candidates:
                # This will tell you if it was SAFETY, RECITATION, or OTHER
                logger.error(f"  Finish Reason: {response.candidates[0].finish_reason}")
                logger.error(f"  Safety Ratings: {response.candidates[0].safety_ratings}")
            logger.error("=" * 70)
            return []
        
        # LOG RESPONSE
        logger.info("=" * 70)
        logger.info("🤖 GEMINI LLM RESPONSE:")
        logger.info("  Candidates: %d", len(response.candidates) if response.candidates else 0)
        if response.candidates:
            for i, candidate in enumerate(response.candidates):
                logger.info("  Candidate %d:", i)
                logger.info("    Finish reason: %s", candidate.finish_reason if hasattr(candidate, 'finish_reason') else 'N/A')
                if hasattr(candidate.content, 'parts'):
                    logger.info("    Parts: %d", len(candidate.content.parts))
                    for j, part in enumerate(candidate.content.parts):
                        # Capture internal reasoning/thinking
                        if hasattr(part, 'thought') and part.thought:
                            logger.info("    Part %d: 💭 THOUGHT:", j)
                            logger.info("      %s", part.text[:500] if hasattr(part, 'text') and part.text else "")
                        
                        # Capture actual tool calls
                        elif hasattr(part, 'function_call') and part.function_call:
                            logger.info("    Part %d: 🛠️ TOOL CALL - %s", j, part.function_call.name)
                            logger.info("      Args: %s", {k: v for k, v in part.function_call.args.items()} if part.function_call.args else {})
                        
                        # Capture text responses
                        elif hasattr(part, 'text') and part.text:
                            logger.info("    Part %d: 🤖 TEXT RESPONSE:", j)
                            logger.info("      %s", part.text[:500] if len(part.text) > 500 else part.text)
        logger.info("=" * 70)
        
        results: list[ToolCall] = []
        
        # Parse Parts (including Thoughts and Function Calls)
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    # Capture actual tool calls
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        # Convert MapComposite to standard dict
                        params = {k: v for k, v in fc.args.items()} if fc.args else {}
                        depends_on = params.pop("depends_on", [])
                        if isinstance(depends_on, str):
                            depends_on = [depends_on]
                        results.append(ToolCall(
                            name=fc.name,
                            params=params,
                            depends_on=depends_on,
                            call_id=fc.name,  # Gemini doesn't provide call IDs
                        ))
        
        return results

    async def _gemini_complete(self, system: str, user: str) -> str:
        import google.generativeai as genai
        
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
        )
        
        response = await model.generate_content_async(
            user,
            generation_config=genai.GenerationConfig(
                max_output_tokens=4096,
                temperature=1.0,
            ),
        )
        
        return response.text if response.text else ""

    def _to_gemini_tools(self, tools: list[Tool]) -> list:
        """Convert Tool list to Gemini function declarations format."""
        import google.generativeai as genai
        
        function_declarations = []
        for t in tools:
            # Gemini expects parameters without the top-level "type" and "properties" wrapper
            params = dict(t.parameters)
            
            # Extract properties and required fields
            properties = params.get("properties", {})
            required = params.get("required", [])
            
            # Build parameter schema in Gemini format using recursive builder
            gemini_params = {}
            for prop_name, prop_schema in properties.items():
                gemini_params[prop_name] = self._build_gemini_schema(prop_schema)
            
            function_declarations.append(
                genai.protos.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties=gemini_params,
                        required=required,
                    ),
                )
            )
        
        return [genai.protos.Tool(function_declarations=function_declarations)]

    def _build_gemini_schema(self, prop_schema: dict):
        """
        Recursively build Gemini schema from JSON Schema.
        Handles arrays with items, nested objects, and all primitive types.
        """
        import google.generativeai as genai
        
        prop_type = prop_schema.get("type", "string")
        gemini_type = self._map_json_type_to_gemini(prop_type)
        
        schema_args = {
            "type": gemini_type,
            "description": prop_schema.get("description", ""),
        }
        
        # Handle array items (e.g., segment_ids: array of strings)
        if prop_type == "array" and "items" in prop_schema:
            items_schema = self._build_gemini_schema(prop_schema["items"])
            schema_args["items"] = items_schema
        
        # Handle nested object properties
        if prop_type == "object" and "properties" in prop_schema:
            nested_props = {}
            for nested_name, nested_schema in prop_schema["properties"].items():
                nested_props[nested_name] = self._build_gemini_schema(nested_schema)
            schema_args["properties"] = nested_props
            
            # Include required fields for nested objects
            if "required" in prop_schema:
                schema_args["required"] = prop_schema["required"]
        
        # Handle enum constraints
        if "enum" in prop_schema:
            schema_args["enum"] = prop_schema["enum"]
        
        return genai.protos.Schema(**schema_args)

    def _map_json_type_to_gemini(self, json_type: str):
        """Map JSON Schema types to Gemini proto types."""
        import google.generativeai as genai
        
        type_map = {
            "string": genai.protos.Type.STRING,
            "number": genai.protos.Type.NUMBER,
            "integer": genai.protos.Type.INTEGER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }
        return type_map.get(json_type.lower(), genai.protos.Type.STRING)
