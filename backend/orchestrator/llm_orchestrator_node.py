"""
orchestrator/llm_orchestrator_node.py

LLM-based tool orchestration node.

Uses LLM to understand natural language prompts and intelligently call tools.
Replaces keyword-based routing with true AI understanding.
"""

import logging
from typing import Any, Callable, Awaitable
from orchestrator.graph_types import AgentState
from llm.prompts import ORCHESTRATOR_SYSTEM

logger = logging.getLogger(__name__)


def _build_timeline_context(timeline_state: Any) -> dict:
    """
    Build compact timeline context for LLM.
    
    Includes only essential info to keep token count low.
    
    Args:
        timeline_state: TimelineState instance
        
    Returns:
        Dict with segments, current_sequence, counts
    """
    try:
        # Get current sequence (filtered clips)
        current_sequence = timeline_state.get_current_sequence()
        
        # Get all segments (full pool)
        all_segments = timeline_state.get_all_segments()
        
        # Build compact segment list (id, text, duration)
        segments_list = []
        for entry in current_sequence:
            seg = all_segments.get(entry.segment_id)
            if seg:
                segments_list.append({
                    "id": seg.id,
                    "text": seg.text[:100] if seg.text else "",  # Truncate long text
                    "duration": round(seg.duration, 2),
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2)
                })
        
        return {
            "segment_count": len(segments_list),
            "total_segments": len(all_segments),
            "current_sequence": segments_list,
            "is_filtered": len(segments_list) < len(all_segments)
        }
    except Exception as exc:
        logger.warning("Failed to build timeline context: %s", exc)
        return {"segment_count": 0, "current_sequence": []}


def make_llm_orchestrator_node(
    registry: Any,
    timeline_state: Any,
    llm_client: Any,
    config: dict
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """
    Factory function that creates LLM orchestrator node.
    
    The node uses LLM to understand prompts and call appropriate tools.
    
    Args:
        registry: AgentRegistry with all registered agents
        timeline_state: TimelineState (the blackboard)
        llm_client: LLMClient for making LLM calls
        config: Configuration dict
        
    Returns:
        Async function that processes prompts via LLM
    """
    
    async def llm_orchestrator_node(state: AgentState) -> AgentState:
        """
        Process user prompt using LLM to understand intent and call tools.
        
        Flow:
        1. Get all available tools from registry
        2. Build timeline context
        3. Call LLM with tools
        4. Execute tool calls returned by LLM
        5. Build user-friendly response
        
        Args:
            state: AgentState with prompt and project_id
            
        Returns:
            Updated AgentState with results and summary
        """
        project_id = state["project_id"]
        prompt = state["prompt"]
        
        logger.info("🤖 LLM Orchestrator: Processing '%s' for project %s", 
                   prompt[:50], project_id)
        
        try:
            # Get all available tools from registry
            tools = registry.all_tools()
            logger.debug("Available tools: %s", [t.name for t in tools])
            
            # Build timeline context
            timeline_context = _build_timeline_context(timeline_state)
            logger.debug("Timeline context: %d segments in sequence", 
                        timeline_context["segment_count"])
            
            # Get conversation history for context
            history = []
            try:
                timeline_history = timeline_state.get_history()
                # Convert to LLM format: [{"role": "user"|"assistant", "content": "..."}]
                for entry in timeline_history[-6:]:  # Last 3 exchanges
                    if entry.get("prompt"):
                        history.append({"role": "user", "content": entry["prompt"]})
                    if entry.get("summary"):
                        history.append({"role": "assistant", "content": entry["summary"]})
                logger.info("Loaded %d conversation messages from history", len(history))
            except Exception as hist_exc:
                logger.warning("Failed to load history: %s", hist_exc)
                history = []
            
            # Call LLM to understand intent and get tool calls
            logger.info("Calling LLM with %d tools, context, and %d history messages", 
                       len(tools), len(history))
            try:
                tool_calls = await llm_client.tool_call(
                    system=ORCHESTRATOR_SYSTEM,
                    user=prompt,
                    tools=tools,
                    context=timeline_context,
                    history=history
                )
                logger.info("LLM returned %d tool calls: %s", 
                           len(tool_calls), [tc.name for tc in tool_calls])
            except Exception as llm_exc:
                logger.exception("LLM call failed: %s", llm_exc)
                return {
                    **state,
                    "results": [],
                    "success": False,
                    "summary": f"LLM call failed: {str(llm_exc)}",
                    "error": str(llm_exc)
                }
            
            # If no tool calls, LLM chose not to call anything
            if not tool_calls:
                logger.warning("LLM returned no tool calls for prompt: %s", prompt)
                return {
                    **state,
                    "results": [],
                    "success": False,
                    "summary": "I'm not sure how to help with that. Could you rephrase your request?",
                    "error": "LLM didn't use any tools"
                }
            
            # Execute each tool call
            results = []
            for i, tool_call in enumerate(tool_calls, 1):
                logger.info("[%d/%d] Executing tool: %s with params: %s", 
                           i, len(tool_calls), tool_call.name, tool_call.params)
                
                # Get agent that owns this tool
                agent = registry.get_agent(tool_call.name)
                
                if agent is None:
                    error_msg = f"Tool '{tool_call.name}' not found in registry"
                    logger.error(error_msg)
                    results.append({
                        "tool": tool_call.name,
                        "success": False,
                        "error": error_msg
                    })
                    continue
                
                # Execute tool
                try:
                    result = await agent.execute_tool(tool_call.name, tool_call.params)
                    
                    if result.success:
                        logger.info("✓ Tool %s succeeded", tool_call.name)
                        results.append({
                            "tool": tool_call.name,
                            "success": True,
                            "data": result.data
                        })
                    else:
                        logger.warning("✗ Tool %s failed: %s", tool_call.name, result.error)
                        results.append({
                            "tool": tool_call.name,
                            "success": False,
                            "error": result.error
                        })
                        
                except Exception as exc:
                    logger.exception("Tool execution failed: %s", exc)
                    results.append({
                        "tool": tool_call.name,
                        "success": False,
                        "error": str(exc)
                    })
            
            # Build summary from results
            success_count = sum(1 for r in results if r.get("success"))
            total_count = len(results)
            
            if success_count == 0:
                # All failed
                errors = [r.get("error", "Unknown error") for r in results if not r.get("success")]
                summary = f"Sorry, I couldn't complete that request. {'; '.join(errors)}"
                overall_success = False
            elif success_count == total_count:
                # All succeeded - build friendly summary
                summary = _build_success_summary(results, prompt)
                overall_success = True
            else:
                # Partial success
                summary = f"Completed {success_count}/{total_count} operations. Some operations failed."
                overall_success = False
            
            logger.info("LLM Orchestrator complete: %d/%d tools succeeded", 
                       success_count, total_count)
            
            # Save timeline if any modifications happened
            if success_count > 0:
                timeline_state.save()
            
            return {
                **state,
                "results": results,
                "success": overall_success,
                "summary": summary,
                "tool_calls": [{"name": tc.name, "params": tc.params} for tc in tool_calls],
                "error": None if overall_success else "Some operations failed"
            }
            
        except Exception as exc:
            logger.exception("LLM Orchestrator failed: %s", exc)
            return {
                **state,
                "results": [],
                "success": False,
                "summary": f"Sorry, something went wrong: {str(exc)}",
                "error": str(exc)
            }
    
    return llm_orchestrator_node


def _build_success_summary(results: list[dict], original_prompt: str) -> str:
    """
    Build user-friendly summary from successful tool results.
    
    Consolidates repeated operations into a single message.
    
    Args:
        results: List of tool execution results
        original_prompt: Original user prompt
        
    Returns:
        Human-readable summary string
    """
    # Group results by tool type for consolidation
    tool_groups = {}
    search_text = None
    
    for result in results:
        if not result.get("success"):
            continue
            
        tool_name = result.get("tool", "")
        data = result.get("data", {})
        
        # Group by tool name
        if tool_name not in tool_groups:
            tool_groups[tool_name] = []
        tool_groups[tool_name].append(data)
        
        # Capture search full_text for display
        if tool_name.startswith("search.") and data.get("full_text"):
            search_text = data.get("full_text")
    
    # Build consolidated summaries
    summaries = []
    
    for tool_name, data_list in tool_groups.items():
        count = len(data_list)
        
        if tool_name.startswith("conversation."):
            # Return the conversation message directly
            message = data_list[0].get("message", "")
            if message:
                return message  # Don't add checkmark for conversations
        
        elif tool_name.startswith("search."):
            total_segments = sum(len(d.get("segment_ids", [])) for d in data_list)
            summaries.append(f"✅ Found {total_segments} clip{'s' if total_segments != 1 else ''}")
            if search_text:
                summaries.append(f"\n\n{search_text}")
                
        elif tool_name.startswith("edit."):
            if "keep_only" in tool_name:
                summaries.append(f"✅ Updated timeline")
            elif "trim" in tool_name:
                summaries.append(f"✅ Trimmed {count} segment{'s' if count != 1 else ''}")
            elif "transition" in tool_name:
                trans_type = data_list[0].get("type", "transition")
                summaries.append(f"✅ Added {trans_type} transition to {count} clip{'s' if count != 1 else ''}")
            elif "effect" in tool_name:
                effect_type = data_list[0].get("effect_type", "effect")
                summaries.append(f"✅ Added {effect_type} to {count} clip{'s' if count != 1 else ''}")
            elif "reorder" in tool_name:
                summaries.append(f"✅ Reordered clips")
            else:
                summaries.append(f"✅ Applied {count} edit{'s' if count != 1 else ''}")
                
        elif tool_name.startswith("export."):
            summaries.append(f"✅ Video exported successfully")
        else:
            # Generic success message
            summaries.append(f"✅ Completed {count} operation{'s' if count != 1 else ''}")
    
    # Join summaries
    if summaries:
        return " ".join(summaries)
    else:
        return "Done!"
