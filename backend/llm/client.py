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
import os
from typing import Any

from agents.base import Tool, ToolCall


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

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def tool_call(
        self,
        system: str,
        user: str,
        tools: list[Tool],
        context: dict | None = None,
    ) -> list[ToolCall]:
        """
        Make a single LLM call that returns tool invocations.

        The model reads the system prompt, user message, and available tools,
        then returns a list of ToolCall objects (name + params).
        """
        if context:
            user = user + "\n\n<context>\n" + json.dumps(context, indent=2) + "\n</context>"

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
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        anthropic_tools = self._to_anthropic_tools(tools)

        response = await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=anthropic_tools,
            messages=[{"role": "user", "content": user}],
            tool_choice={"type": "auto"},
        )

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
            tool_choice="auto",
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
        import google.generativeai as genai
        
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
        )
        
        gemini_tools = self._to_gemini_tools(tools)
        
        # Gemini expects a combined prompt (system is set in GenerativeModel)
        response = await model.generate_content_async(
            user,
            tools=gemini_tools,
            generation_config=genai.GenerationConfig(
                max_output_tokens=4096,
                temperature=1.0,
            ),
        )
        
        results: list[ToolCall] = []
        
        # Check if model wants to call functions
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        params = dict(fc.args) if fc.args else {}
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
