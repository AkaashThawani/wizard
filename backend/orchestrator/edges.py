"""
orchestrator/edges.py

Conditional edge functions for LangGraph routing.

Controls the flow between transcription and analysis phases,
ensuring proper sequential execution.
"""

import logging
from orchestrator.graph_types import AgentState

logger = logging.getLogger(__name__)


def route_after_transcription(state: AgentState) -> str:
    """
    Route after transcription phase completes.
    
    Always proceeds to analysis phase if transcription succeeded.
    Routes to error handler if transcription failed.
    
    Returns:
        "analysis_phase" if success, "error_handler" if failed
    """
    if state.get("transcription_done") and state.get("success"):
        logger.debug("Routing to analysis phase after successful transcription")
        return "analysis_phase"
    
    logger.warning("Transcription failed, routing to error handler")
    return "error_handler"


def route_after_analysis(state: AgentState) -> str:
    """
    Route after analysis phase completes.
    
    Always proceeds to END since analysis is the final phase.
    
    Returns:
        "END"
    """
    logger.debug("Analysis complete, ending workflow")
    return "END"


def should_retry_on_failure(state: AgentState) -> str:
    """
    Determine if a failed operation should be retried.
    
    For now, no retry logic - just route to error handler.
    Future: Add retry for network errors, timeouts, etc.
    
    Returns:
        "error_handler" always
    """
    error = state.get("error", "Unknown error")
    logger.info("Failure detected: %s - routing to error handler (no retry)", error)
    return "error_handler"
