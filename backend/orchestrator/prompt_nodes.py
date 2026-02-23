"""
orchestrator/prompt_nodes.py

Agent nodes for the prompt workflow.

Each node wraps an agent's execute_tool() method for use in LangGraph.
All nodes run in parallel after intent detection since they operate on
existing TimelineState data (transcription + features already exist).
Uses factory functions with closures to inject dependencies.
"""

import logging
from typing import Any, Callable, Awaitable
from orchestrator.graph_types import AgentState

logger = logging.getLogger(__name__)


def make_search_node(registry: Any) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for search node."""
    
    async def search_node(state: AgentState) -> AgentState:
        """Execute SearchAgent to find segments matching the prompt."""
        project_id = state["project_id"]
        prompt = state["prompt"]
        
        logger.info("🔍 SearchAgent: Processing prompt for project %s", project_id)
        
        try:
            search_agent = registry.get_agent("search.find_segments")
            
            if search_agent is None:
                logger.warning("SearchAgent not found in registry")
                return {"error": ["SearchAgent not available"]}
            
            # Extract search query from prompt (simple approach - use full prompt)
            result = await search_agent.execute_tool("search.find_segments", {"query": prompt})
            
            if result.success:
                # Format user-friendly summary
                segment_ids = result.data.get("segment_ids", [])
                full_text = result.data.get("full_text", "")
                
                summary = f"✅ Found {len(segment_ids)} clips matching '{prompt}'\n\n{full_text}"
                
                logger.info("✓ SearchAgent complete: %d segments", len(segment_ids))
                return {
                    "results": state.get("results", []) + [{
                        **result.data,
                        "summary": summary  # Add user-friendly summary
                    }],
                    "success": True
                }
            else:
                logger.warning("SearchAgent failed: %s", result.error)
                return {"error": [result.error] if result.error else []}
                
        except Exception as exc:
            logger.exception("SearchAgent error: %s", exc)
            return {"error": [str(exc)]}
    
    return search_node


def make_edit_node(registry: Any, timeline_state: Any, llm_client: Any) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for edit node."""
    
    async def edit_node(state: AgentState) -> AgentState:
        """Execute EditAgent to modify the timeline."""
        project_id = state["project_id"]
        prompt = state["prompt"]
        
        logger.info("✂️ EditAgent: Processing prompt for project %s", project_id)
        
        try:
            # Get EditAgent via any of its tools
            edit_agent = registry.get_agent("edit.keep_only")
            
            if edit_agent is None:
                logger.warning("EditAgent not found in registry")
                return {"error": ["EditAgent not available"]}
            
            # Note: EditAgent doesn't have a generic "apply" tool
            # This node needs LLM to parse prompt and call specific edit tools
            # For now, return error - edit operations should be called directly via specific tools
            return {"error": ["Edit operations require specific tool calls (e.g., edit.keep_only, edit.trim_segment)"]}
                
        except Exception as exc:
            logger.exception("EditAgent error: %s", exc)
            return {"error": [str(exc)]}
    
    return edit_node


def make_export_node(registry: Any) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for export node."""
    
    async def export_node(state: AgentState) -> AgentState:
        """Execute ExportAgent to render the video."""
        project_id = state["project_id"]
        prompt = state["prompt"]
        
        logger.info("📹 ExportAgent: Processing prompt for project %s", project_id)
        
        try:
            export_agent = registry.get_agent("export.export")
            
            if export_agent is None:
                logger.warning("ExportAgent not found in registry")
                return {"error": ["ExportAgent not available"]}
            
            # Determine resolution from prompt (default: preview)
            resolution = "preview"
            if "full" in prompt.lower() or "1080" in prompt or "720" in prompt:
                resolution = "full"
            
            result = await export_agent.execute_tool("export.export", {
                "resolution": resolution
            })
            
            if result.success:
                logger.info("✓ ExportAgent complete: %s", result.data.get("output_path", ""))
                return {
                    "results": state.get("results", []) + [result.data],
                    "success": True
                }
            else:
                logger.warning("ExportAgent failed: %s", result.error)
                return {"error": [result.error] if result.error else []}
                
        except Exception as exc:
            logger.exception("ExportAgent error: %s", exc)
            return {"error": [str(exc)]}
    
    return export_node


def make_color_analyze_node(registry: Any, timeline_state: Any) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for color analyzer node."""
    
    async def color_analyze_node(state: AgentState) -> AgentState:
        """Execute ColorAgent to (re-)analyze visual features."""
        project_id = state["project_id"]
        
        logger.info("🎨 ColorAgent: Analyzing visual features for project %s", project_id)
        
        try:
            color_agent = registry.get_agent("color.analyze")
            
            if color_agent is None:
                logger.warning("ColorAgent not found in registry")
                return {"error": ["ColorAgent not available"]}
            
            result = await color_agent.execute_tool("color.analyze", {})
            
            if result.success:
                logger.info("✓ ColorAgent complete")
                timeline_state.save()
                return {
                    "results": state.get("results", []) + [result.data],
                    "success": True
                }
            else:
                logger.warning("ColorAgent failed: %s", result.error)
                return {"error": [result.error] if result.error else []}
                
        except Exception as exc:
            logger.exception("ColorAgent error: %s", exc)
            return {"error": [str(exc)]}
    
    return color_analyze_node


def make_audio_analyze_node(registry: Any, timeline_state: Any) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for audio analyzer node."""
    
    async def audio_analyze_node(state: AgentState) -> AgentState:
        """Execute AudioAgent to (re-)analyze audio features."""
        project_id = state["project_id"]
        
        logger.info("🎵 AudioAgent: Analyzing audio features for project %s", project_id)
        
        try:
            audio_agent = registry.get_agent("audio.analyze")
            
            if audio_agent is None:
                logger.warning("AudioAgent not found in registry")
                return {"error": ["AudioAgent not available"]}
            
            result = await audio_agent.execute_tool("audio.analyze", {})
            
            if result.success:
                logger.info("✓ AudioAgent complete")
                timeline_state.save()
                return {
                    "results": state.get("results", []) + [result.data],
                    "success": True
                }
            else:
                logger.warning("AudioAgent failed: %s", result.error)
                return {"error": [result.error] if result.error else []}
                
        except Exception as exc:
            logger.exception("AudioAgent error: %s", exc)
            return {"error": [str(exc)]}
    
    return audio_analyze_node
