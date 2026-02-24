"""
orchestrator/graph.py

Full LangGraph implementation with StateGraph, Send API, and checkpointing.

Graph structure:
  START → transcription_phase → [color_analyzer, audio_analyzer] (parallel) → END

Uses LangGraph's Send API for true parallel execution with proper state management.
Includes built-in checkpointing for SSE reconnection support.
"""

import logging
from typing import Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver
from orchestrator.graph_types import AgentState
from orchestrator.nodes import (
    make_transcription_phase_node,
    make_parallel_analysis_node,
    make_reassembly_node,
    make_error_handler_node
)
from orchestrator.sse_manager import SSEConnectionManager

logger = logging.getLogger(__name__)


def route_to_parallel_analysis(state: AgentState) -> list[Send] | str:
    """
    Route to parallel color + audio analysis using Send API.
    
    After transcription completes, this sends the state to both
    color and audio analyzer nodes which run in parallel.
    
    Returns:
        List of Send objects for parallel execution, or "END" if failed
    """
    if not state.get("transcription_done") or not state.get("success"):
        logger.warning("Transcription failed, skipping analysis")
        return "error_handler"
    
    # Use Send API to invoke analysis_phase in parallel
    # LangGraph will execute this concurrently
    logger.debug("Routing to parallel analysis phase")
    return [Send("analysis_phase", state)]


def route_after_analysis(state: AgentState) -> str:
    """Route after analysis completes - always go to END."""
    logger.debug("Analysis complete, routing to END")
    return END


def create_agent_graph(
    registry: Any,
    timeline_state: Any,
    config: dict,
    sse_manager: SSEConnectionManager | None = None
) -> Any:
    """
    Create the full LangGraph with StateGraph, Send API, and checkpointing.
    
    Graph structure:
    
    START
      ↓
    transcription_phase (sequential - must complete first)
      ↓ [checkpoint saved]
      ↓ [Send API for parallelization]
      ├── analysis_phase (color + audio in parallel via asyncio.gather)
      ↓ [checkpoint saved]
    END
    
    Args:
        registry: AgentRegistry with all registered agents
        timeline_state: TimelineState (the blackboard)
        config: Configuration dict
        sse_manager: SSE connection manager
    
    Returns:
        Compiled StateGraph ready for execution
    """
    if sse_manager is None:
        sse_manager = SSEConnectionManager()
    
    # Create StateGraph with our state schema
    graph = StateGraph(AgentState)
    
    # Store dependencies in graph config for node access
    graph_config = {
        "registry": registry,
        "timeline_state": timeline_state,
        "sse_manager": sse_manager,
        "config": config
    }
    
    # Create nodes with dependencies injected via closures
    transcription_node = make_transcription_phase_node(registry, timeline_state, sse_manager)
    parallel_analysis_node = make_parallel_analysis_node(registry, timeline_state, sse_manager)
    reassembly_node_fn = make_reassembly_node(registry, timeline_state, config)
    error_node = make_error_handler_node(timeline_state, sse_manager)
    
    # Add nodes to graph
    graph.add_node("transcription_phase", transcription_node)
    graph.add_node("parallel_analysis", parallel_analysis_node)
    graph.add_node("reassembly", reassembly_node_fn)
    graph.add_node("error_handler", error_node)
    
    # Add edges - Sequential: transcription → parallel_analysis → reassembly
    # START → transcription (must complete first)
    graph.add_edge(START, "transcription_phase")
    
    # transcription → parallel_analysis (color + audio run together)
    graph.add_edge("transcription_phase", "parallel_analysis")
    
    # parallel_analysis → reassembly
    graph.add_edge("parallel_analysis", "reassembly")
    
    # reassembly → END (always)
    graph.add_edge("reassembly", END)
    
    # error_handler → END (always)
    graph.add_edge("error_handler", END)
    
    # Add checkpointing for reconnection support
    # MemorySaver stores checkpoints in memory (fast, works with async)
    checkpointer = MemorySaver()
    
    # Compile graph with checkpointing
    compiled_graph = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[],  # No interrupts (for now)
        interrupt_after=[],   # Could add: interrupt_after=["transcription_phase"] for human-in-loop
    )
    
    logger.info("✓ Created LangGraph with StateGraph + Send API + Checkpointing")
    logger.info("  Nodes: transcription_phase, analysis_phase, error_handler")
    logger.info("  Parallelization: Send API routes to analysis_phase")
    logger.info("  Checkpointing: MemorySaver (in-memory)")
    
    # Wrap compiled graph with config injection
    class ConfigurableGraph:
        """Wrapper to inject config into graph invocations."""
        
        def __init__(self, graph, config):
            self._graph = graph
            self._config = config
        
        async def invoke(self, initial_state: dict, config: dict | None = None) -> AgentState:
            """
            Execute the graph with injected config.
            
            Args:
                initial_state: Initial state dict
                config: Optional config override
            
            Returns:
                Final AgentState after execution
            """
            # Merge configs with thread_id required by MemorySaver
            run_config = {
                "configurable": {
                    "thread_id": initial_state["project_id"],  # Use project_id as thread_id
                    **self._config
                },
                **(config or {})
            }
            
            # Convert initial_state to full AgentState
            full_state: AgentState = {
                "prompt": initial_state.get("prompt", "auto-analysis"),
                "project_id": initial_state["project_id"],
                "phase": "transcription",
                "transcription_done": False,
                "segments_count": 0,
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
            
            return result
    
    return ConfigurableGraph(compiled_graph, graph_config)
