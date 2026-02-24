"""
chat_workflow.py

Chat workflow using LangGraph's built-in ReAct agent.

The ReAct agent automatically handles:
- Multi-step planning (solves Gap 1)
- Tool calling with LLM
- Re-planning based on results
- Conversation memory
"""

import logging
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from llm.prompts import ORCHESTRATOR_SYSTEM

logger = logging.getLogger(__name__)


def create_chat_workflow(
    registry: Any,
    timeline_state: Any,
    llm_client: Any,
    config: dict
) -> Any:
    """
    Create chat workflow using LangGraph's ReAct agent.
    
    The ReAct agent pattern:
    1. Thought: Reason about what to do
    2. Action: Call a tool
    3. Observation: See tool result
    4. Repeat until task complete
    
    Args:
        registry: AgentRegistry with all tools
        timeline_state: TimelineState (the blackboard)
        llm_client: LLMClient wrapper
        config: Configuration dict
    
    Returns:
        Compiled LangGraph agent
    """
    from pathlib import Path
    import sqlite3
    import atexit

    # Get all tools from registry
    tools = registry.all_tools()
    logger.info("Creating ReAct agent with %d tools", len(tools))
    
    # Convert our Tool objects to LangChain tool format
    langchain_tools = _convert_tools_to_langchain(tools, registry)
    
    # Get underlying LangChain chat model from our wrapper
    chat_model = _get_langchain_model(llm_client)
    
    # NOTE: We rely on strong system prompt instructions instead of provider-specific
    # tool_choice bindings, since not all providers (like Gemini) support it.
    # The enhanced ORCHESTRATOR_SYSTEM prompt explicitly requires tool usage.
    logger.info("Using system prompt to enforce tool usage (works with all providers)")
    
    # Create system message with timeline context
    system_prompt = _build_system_message(timeline_state)
    
    print("=" * 80)
    print("🔧 DEBUG: REACT AGENT CONFIGURATION")
    print(f"Tools count: {len(langchain_tools)}")
    print("\n📋 AVAILABLE TOOLS:")
    for i, tool in enumerate(langchain_tools, 1):
        print(f"  {i}. {tool.name}")
        print(f"     Description: {tool.description}")
    
    print(f"\n📝 FULL SYSTEM PROMPT:")
    print(system_prompt)
    print("=" * 80)
    
    # Use user home directory for database (guaranteed writable on all platforms)
    base_dir = Path.home() / ".wizard"
    base_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = base_dir / "checkpoints.db"
    
    logger.info("Using checkpoints database at: %s", db_path)
    
    # For now, use None checkpointer to get things working
    # We can add persistence back later once the basic agent works
    checkpointer = None
    logger.warning("Checkpointer disabled - conversations won't persist across restarts")
    
    # Create agent without checkpointer
    agent = create_react_agent(
        model=chat_model,
        tools=langchain_tools,
        prompt=system_prompt,
        checkpointer=checkpointer,
    )
    
    logger.info("✓ Created ReAct agent with %d tools", len(langchain_tools))
    
    return agent


def _convert_tools_to_langchain(tools: list, registry: Any) -> list:
    """
    Convert our Tool dataclasses to LangChain tool format.
    
    LangChain tools need:
    - name: str
    - description: str
    - func: callable that executes the tool
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, create_model
    
    langchain_tools = []
    
    for tool in tools:
        # Create Pydantic model from JSON schema for args_schema
        # LangChain expects Pydantic models, not raw JSON schema
        properties = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])
        
        # Build field definitions for Pydantic
        fields = {}
        for prop_name, prop_info in properties.items():
            field_type = str  # Default to string
            field_default = ... if prop_name in required else None
            
            # Map JSON types to Python types
            if prop_info.get("type") == "array":
                # Handle array types with proper item types (required by Gemini)
                items = prop_info.get("items", {})
                item_type = items.get("type", "string")
                
                if item_type == "string":
                    field_type = list[str]
                elif item_type == "integer":
                    field_type = list[int]
                elif item_type == "number":
                    field_type = list[float]
                elif item_type == "boolean":
                    field_type = list[bool]
                else:
                    field_type = list  # Fallback for unknown types
            elif prop_info.get("type") == "number":
                field_type = float
            elif prop_info.get("type") == "integer":
                field_type = int
            elif prop_info.get("type") == "boolean":
                field_type = bool
            
            fields[prop_name] = (field_type, field_default)
        
        # Create Pydantic model dynamically
        ToolArgsModel = create_model(
            f"{tool.name.replace('.', '_')}_Args",
            **fields
        )
        
        # Create async function that executes this tool
        # Using closure to capture tool.name
        def make_executor(tool_name: str):
            async def execute_tool(**kwargs):
                agent = registry.get_agent(tool_name)
                if agent is None:
                    return {"error": f"Tool {tool_name} not found"}
                
                result = await agent.execute_tool(tool_name, kwargs)
                
                if result.success:
                    return result.data
                else:
                    return {"error": result.error}
            return execute_tool
        
        # Create LangChain tool
        lc_tool = StructuredTool(
            name=tool.name,
            description=tool.description,
            func=make_executor(tool.name),
            coroutine=make_executor(tool.name),  # For async
            args_schema=ToolArgsModel
        )
        
        langchain_tools.append(lc_tool)
    
    return langchain_tools


def _get_langchain_model(llm_client: Any):
    """
    Get LangChain chat model from our LLMClient wrapper.
    
    Our LLMClient wraps Anthropic/OpenAI/Gemini.
    Imports are conditional - only loads the provider you're actually using.
    """
    provider = llm_client.provider
    model = llm_client.model
    api_key = llm_client.api_key
    
    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model,
                anthropic_api_key=api_key,
                max_tokens=4096
            )
        except ImportError:
            raise ValueError("langchain-anthropic not installed. Install with: pip install langchain-anthropic")
            
    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                openai_api_key=api_key
            )
        except ImportError:
            raise ValueError("langchain-openai not installed. Install with: pip install langchain-openai")
            
    elif provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                convert_system_message_to_human=True,  # Gemini doesn't support system messages natively
            )
        except ImportError:
            raise ValueError("langchain-google-genai not installed. Install with: pip install langchain-google-genai")
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _build_system_message(timeline_state: Any) -> str:
    """
    Build system message with timeline context.
    
    Includes current timeline state so agent knows what it's working with.
    """
    # Get timeline summary
    segment_count = timeline_state.segment_count()
    sequence = timeline_state.get_current_sequence()
    video_duration = timeline_state.video_duration
    
    context = f"""
Current timeline state:
- Video duration: {video_duration:.1f}s
- Total segments: {segment_count}
- Current sequence: {len(sequence)} segments
- Source: {timeline_state.get_source().get('filename', 'Unknown')}

{ORCHESTRATOR_SYSTEM}
"""
    
    return context


async def invoke_chat_workflow(
    agent: Any,
    project_id: str,
    prompt: str,
    timeline_state: Any
) -> dict:
    """
    Invoke the ReAct agent with a user prompt.
    
    The agent will automatically:
    1. Reason about the task
    2. Call tools as needed
    3. Re-plan based on results
    4. Return when complete
    
    Args:
        agent: Compiled ReAct agent
        project_id: Project ID (used as thread_id for checkpointing)
        prompt: User's natural language request
        timeline_state: Current timeline state
    
    Returns:
        Dict with success, summary, results
    """
    # Build input messages
    messages = [HumanMessage(content=prompt)]
    
    # Invoke agent with thread_id for checkpointing
    config = {"configurable": {"thread_id": project_id}}
    
    try:
        logger.info("Invoking ReAct agent for project %s: %s", project_id, prompt[:50])
        
        print("=" * 80)
        print("🔍 DEBUG: INVOKING REACT AGENT")
        print(f"Project: {project_id}")
        print(f"Prompt: {prompt}")
        print(f"Input messages: {len(messages)}")
        print(f"Message 0: {messages[0].__class__.__name__} - {messages[0].content[:100]}")
        print("=" * 80)
        
        # Agent runs until complete or max iterations
        result = await agent.ainvoke(
            {"messages": messages},
            config=config
        )
        
        print("=" * 80)
        print("🔍 DEBUG: AGENT RESPONSE RECEIVED")
        print(f"Result keys: {result.keys()}")
        print(f"Total messages in result: {len(result['messages'])}")
        print("\n📨 MESSAGE BREAKDOWN:")
        
        for i, msg in enumerate(result["messages"]):
            msg_type = msg.__class__.__name__
            print(f"\n  Message {i}: {msg_type}")
            
            if hasattr(msg, 'content'):
                content_preview = str(msg.content)[:200] if msg.content else "(empty)"
                print(f"    Content: {content_preview}")
            
            if hasattr(msg, 'tool_calls'):
                print(f"    Has tool_calls attr: {msg.tool_calls is not None}")
                if msg.tool_calls:
                    print(f"    Tool calls count: {len(msg.tool_calls)}")
                    for tc in msg.tool_calls:
                        print(f"      - {tc.get('name')}: {tc.get('args', {})}")
            
            if hasattr(msg, 'tool_call_id'):
                print(f"    Tool call ID: {msg.tool_call_id}")
        
        # Extract final message from agent
        final_message = result["messages"][-1]
        
        print("\n🎯 FINAL MESSAGE:")
        print(f"  Type: {final_message.__class__.__name__}")
        print(f"  Content: {final_message.content if hasattr(final_message, 'content') else 'N/A'}")
        print(f"  Has tool_calls: {hasattr(final_message, 'tool_calls') and final_message.tool_calls is not None}")
        
        # Parse results from agent's actions
        # ReAct agent stores tool calls in the message history
        tool_calls = _extract_tool_calls_from_messages(result["messages"])
        
        print(f"\n✅ EXTRACTED TOOL CALLS: {len(tool_calls)}")
        for tc in tool_calls:
            print(f"  - {tc.get('tool')}: {tc.get('params', {})}")
            if 'result' in tc:
                print(f"    Result: {tc['result']}")
        print("=" * 80)
        
        logger.info("✓ ReAct agent complete: %d tool calls", len(tool_calls))
        
        return {
            "success": True,
            "summary": final_message.content if hasattr(final_message, 'content') else "Complete",
            "results": tool_calls,
            "messages": result["messages"]
        }
        
    except Exception as exc:
        print("=" * 80)
        print("❌ ERROR in invoke_chat_workflow:")
        print(f"  {type(exc).__name__}: {str(exc)}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        logger.exception("Chat workflow error: %s", exc)
        return {
            "success": False,
            "summary": f"Error: {str(exc)}",
            "results": [],
            "error": str(exc)
        }


def _extract_tool_calls_from_messages(messages: list) -> list[dict]:
    """
    Extract tool calls and results from message history for result formatting.
    
    LangGraph message flow:
    1. AIMessage with tool_calls (the request)
    2. ToolMessage with content (the result)
    
    We need to match them together to get both params and results.
    """
    from langchain_core.messages import AIMessage, ToolMessage
    
    tool_calls = []
    
    # Build a map of tool_call_id -> result for quick lookup
    tool_results = {}
    for msg in messages:
        if isinstance(msg, ToolMessage):
            # ToolMessage contains the result
            tool_results[msg.tool_call_id] = msg.content
    
    # Now extract tool calls and match with results
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                # Handle both dict and object formats
                if isinstance(tc, dict):
                    tool_call_id = tc.get("id")
                    tool_name = tc.get("name")
                    tool_args = tc.get("args", {})
                else:
                    # Object with attributes
                    tool_call_id = getattr(tc, "id", None)
                    tool_name = getattr(tc, "name", None)
                    tool_args = getattr(tc, "args", {})
                
                # Get the result for this tool call
                result_content = tool_results.get(tool_call_id, {})
                
                # Parse result content (it may be a dict or string)
                if isinstance(result_content, dict):
                    result_data = result_content
                elif isinstance(result_content, str):
                    # Try to parse as JSON
                    try:
                        import json
                        result_data = json.loads(result_content)
                    except:
                        result_data = {"raw": result_content}
                else:
                    result_data = {}
                
                tool_calls.append({
                    "tool": tool_name,
                    "params": tool_args,
                    "result": result_data,  # Include the actual result!
                    "success": True  # Assume success if in history
                })
    
    return tool_calls
