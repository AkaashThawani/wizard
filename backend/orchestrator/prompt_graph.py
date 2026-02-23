"""
orchestrator/prompt_graph.py

LangGraph for handling manual user prompts.

Uses LLM-based orchestration to understand natural language and call tools intelligently.
Replaces keyword-based routing with true AI understanding.
"""

import logging
from typing import Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from orchestrator.graph_types import AgentState
from orchestrator.llm_orchestrator_node import make_llm_orchestrator_node

logger = logging.getLogger(__name__)


def create_prompt_workflow(
    registry: Any,
    timeline_state: Any,
    llm_client: Any,
    config: dict
) -> Any:
    """
    Create prompt workflow with LLM-based orchestration.
    
    Graph structure:
    START → llm_orchestrator → END
    
    The LLM orchestrator uses AI to understand natural language prompts
    and intelligently call the appropriate tools.
    
    Args:
        registry: AgentRegistry
        timeline_state: TimelineState (blackboard)
        llm_client: LLMClient for making LLM calls
        config: Configuration dict
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create StateGraph
    graph = StateGraph(AgentState)
    
    # Store dependencies in config
    graph_config = {
        "registry": registry,
        "timeline_state": timeline_state,
        "llm_client": llm_client,
        "config": config
    }
    
    # Create LLM orchestrator node
    llm_orchestrator = make_llm_orchestrator_node(registry, timeline_state, llm_client, config)
    
    # Add single orchestrator node to graph
    graph.add_node("llm_orchestrator", llm_orchestrator)
    
    # Simple linear flow: START → llm_orchestrator → END
    graph.add_edge(START, "llm_orchestrator")
    graph.add_edge("llm_orchestrator", END)
    
    # Add checkpointing
    # MemorySaver stores checkpoints in memory (fast, works with async)
    checkpointer = MemorySaver()
    
    # Compile graph
    compiled_graph = graph.compile(checkpointer=checkpointer)
    
    logger.info("✓ Created prompt workflow with LLM orchestration")
    logger.info("  Nodes: llm_orchestrator")
    logger.info("  Flow: START → LLM understands prompt → calls tools → END")
    
    # Wrap with config injection
    class ConfigurablePromptGraph:
        """Wrapper to inject config into graph invocations."""
        
        def __init__(self, graph, config):
            self._graph = graph
            self._config = config
        
        async def invoke(self, initial_state: dict, config: dict | None = None) -> AgentState:
            """
            Execute the prompt workflow.
            
            Args:
                initial_state: Must contain project_id and prompt
                config: Optional config override
            
            Returns:
                Final AgentState with results from all executed agents
            """
            # Merge configs with thread_id required by MemorySaver
            run_config = {
                "configurable": {
                    "thread_id": initial_state["project_id"],  # Use project_id as thread_id
                    **self._config
                },
                **(config or {})
            }
            
            # Convert to full AgentState
            full_state: AgentState = {
                "prompt": initial_state["prompt"],
                "project_id": initial_state["project_id"],
                "phase": "complete",  # Prompts run after analysis is complete
                "transcription_done": True,  # Assume already done
                "segments_count": self._config["timeline_state"].segment_count(),
                "color_done": False,
                "audio_done": False,
                "client_id": None,
                "last_checkpoint": None,
                "tool_calls": [],
                "results": [],
                "messages": [],
                "snapshot_id": self._config["timeline_state"].take_snapshot(),
                "success": False,
                "error": None,
                "summary": None
            }
            
            # Invoke graph
            result = await self._graph.ainvoke(full_state, run_config)
            
            # Don't overwrite summary - llm_orchestrator_node already built it
            # Just ensure success is set if we have results
            if result.get("results") and not result.get("summary"):
                result["summary"] = "Complete"
            
            return result
    
    return ConfigurablePromptGraph(compiled_graph, graph_config)
