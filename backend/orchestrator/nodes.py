"""
orchestrator/nodes.py

LangGraph node functions for 2-phase agent execution.

Phase 1: Transcription (sequential prerequisite)
Phase 2: Visual + Audio analysis (parallel)

Each node updates AgentState and sends SSE progress events.
Uses factory functions with closures to inject dependencies.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable
from orchestrator.graph_types import AgentState, CheckpointMetadata, SSEEvent

logger = logging.getLogger(__name__)


def make_transcription_phase_node(
    registry: Any,
    timeline_state: Any,
    sse_manager: Any
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function that creates transcription node with captured dependencies."""
    
    async def transcription_phase_node(state: AgentState) -> AgentState:
        """
        Phase 1: Transcribe video to extract segments.
        
        This MUST complete before visual/audio analysis can run,
        since they need segments to analyze.
        
        Returns updated state with transcription_done=True.
        """
        project_id = state["project_id"]
        logger.info("🎬 Phase 1: Starting transcription for project %s", project_id)
        
        # Send progress event
        sse_event = SSEEvent(
            event="transcription_start",
            data={"message": "Starting transcription..."},
            checkpoint_id=None
        )
        sse_manager.add_event(project_id, sse_event)
        
        try:
            # Execute TranscriptionAgent
            transcription_agent = registry.get_agent("transcription.transcribe")
            if transcription_agent is None:
                raise ValueError("TranscriptionAgent not found in registry")
            
            result = await transcription_agent.execute_tool("transcription.transcribe", {})
            
            if not result.success:
                logger.error("Transcription failed: %s", result.error)
                return {
                    **state,
                    "phase": "transcription",
                    "transcription_done": False,
                    "success": False,
                    "error": f"Transcription failed: {result.error}"
                }
            
            # Get segment count from timeline
            segments_count = timeline_state.segment_count()
            
            # Create checkpoint
            checkpoint_id = f"trans_{project_id}_{int(time.time())}"
            checkpoint = CheckpointMetadata(
                checkpoint_id=checkpoint_id,
                phase="transcription",
                transcription_done=True,
                color_done=False,
                audio_done=False,
                segments_count=segments_count,
                timestamp=time.time()
            )
            sse_manager.set_checkpoint(project_id, checkpoint)
            
            # Send completion event with checkpoint
            sse_event = SSEEvent(
                event="transcription_done",
                data={
                    "segments_count": segments_count,
                    "message": f"Transcription complete - {segments_count} segments ready"
                },
                checkpoint_id=checkpoint_id
            )
            sse_manager.add_event(project_id, sse_event)
            
            logger.info("✓ Phase 1 complete: %d segments transcribed", segments_count)
            
            # Update state - ONLY transcription-specific keys
            return {
                "transcription_done": True,
                "segments_count": segments_count,
                "last_checkpoint": checkpoint_id,
            }
            
        except Exception as exc:
            logger.exception("Transcription phase failed: %s", exc)
            return {
                **state,
                "phase": "transcription",
                "transcription_done": False,
                "success": False,
                "error": str(exc)
            }
    
    return transcription_phase_node


def make_analysis_phase_node(
    registry: Any,
    timeline_state: Any,
    sse_manager: Any,
    config: dict
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function that creates analysis node with captured dependencies."""
    
    async def analysis_phase_node(state: AgentState) -> AgentState:
        """
        Phase 2: Visual + Audio analysis in parallel.
        
        Runs ColorAgent and AudioAgent concurrently since they
        both depend on transcription but not on each other.
        
        Returns updated state with color_done=True, audio_done=True.
        """
        project_id = state["project_id"]
        logger.info("🎨 Phase 2: Starting visual and audio analysis for project %s", project_id)
        
        # Send progress event
        sse_event = SSEEvent(
            event="analysis_start",
            data={"message": "Starting visual and audio analysis..."},
            checkpoint_id=state.get("last_checkpoint")
        )
        sse_manager.add_event(project_id, sse_event)
        
        # Check if agents are enabled
        color_enabled = config.get("agents", {}).get("color", {}).get("enabled", True)
        audio_enabled = config.get("agents", {}).get("audio", {}).get("enabled", True)
        
        tasks = []
        task_names = []
        
        if color_enabled:
            color_agent = registry.get_agent("color.analyze")
            if color_agent:
                tasks.append(color_agent.execute_tool("color.analyze", {}))
                task_names.append("color")
        
        if audio_enabled:
            audio_agent = registry.get_agent("audio.analyze")
            if audio_agent:
                tasks.append(audio_agent.execute_tool("audio.analyze", {}))
                task_names.append("audio")
        
        if not tasks:
            logger.warning("No analysis agents enabled, skipping analysis phase")
            return {
                **state,
                "phase": "complete",
                "color_done": False,
                "audio_done": False,
                "success": True
            }
        
        # Run analysis in parallel
        logger.info("Running %d analysis agents in parallel: %s", len(tasks), task_names)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        color_done = False
        audio_done = False
        errors = []
        
        for i, (result, name) in enumerate(zip(results, task_names)):
            if isinstance(result, Exception):
                logger.error("%s analysis failed: %s", name.capitalize(), result)
                errors.append(f"{name}: {str(result)}")
            elif hasattr(result, 'success') and result.success:
                if name == "color":
                    color_done = True
                    logger.info("✓ ColorAgent completed")
                elif name == "audio":
                    audio_done = True
                    logger.info("✓ AudioAgent completed")
            else:
                error_msg = result.error if hasattr(result, 'error') else "Unknown error"
                logger.warning("%s analysis returned failure: %s", name.capitalize(), error_msg)
                errors.append(f"{name}: {error_msg}")
        
        # Create final checkpoint
        checkpoint_id = f"analysis_{project_id}_{int(time.time())}"
        checkpoint = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            phase="complete",
            transcription_done=True,
            color_done=color_done,
            audio_done=audio_done,
            segments_count=state.get("segments_count", 0),
            timestamp=time.time()
        )
        sse_manager.set_checkpoint(project_id, checkpoint)
        
        # Send completion event
        sse_event = SSEEvent(
            event="analysis_done",
            data={
                "color_done": color_done,
                "audio_done": audio_done,
                "message": "Analysis complete",
                "errors": errors if errors else None
            },
            checkpoint_id=checkpoint_id
        )
        sse_manager.add_event(project_id, sse_event)
        
        logger.info("✓ Phase 2 complete: color=%s, audio=%s", color_done, audio_done)
        
        return {
            **state,
            "phase": "complete",
            "color_done": color_done,
            "audio_done": audio_done,
            "last_checkpoint": checkpoint_id,
            "success": True,
            "error": "; ".join(errors) if errors else None
        }
    
    return analysis_phase_node


def make_parallel_analysis_node(
    registry: Any,
    timeline_state: Any,
    sse_manager: Any
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for parallel color+audio analysis node."""
    
    async def parallel_analysis_node(state: AgentState) -> AgentState:
        """
        Run ColorAgent and AudioAgent in TRUE parallel using asyncio.gather().
        
        This is faster than LangGraph's Send API which serializes state updates.
        """
        project_id = state["project_id"]
        logger.info("=" * 70)
        logger.info("🚀 PARALLEL ANALYSIS NODE INVOKED")
        logger.info("  Project: %s", project_id)
        logger.info("=" * 70)
        
        visual_timeline = []
        audio_timeline = []
        visual_done = False
        audio_done = False
        
        try:
            # Get agents
            color_agent = registry.get_agent("color.analyze")
            audio_agent = registry.get_agent("audio.analyze")
            
            if not color_agent or not audio_agent:
                raise ValueError("ColorAgent or AudioAgent not found in registry")
            
            # Run BOTH agents in parallel using asyncio.gather()
            logger.info("⚡ Running ColorAgent and AudioAgent concurrently...")
            import time
            start_time = time.time()
            
            visual_timeline, audio_timeline = await asyncio.gather(
                color_agent.analyze_full_video(),
                audio_agent.analyze_full_video(),
                return_exceptions=False  # Raise if either fails
            )
            
            elapsed = time.time() - start_time
            logger.info("✓ PARALLEL analysis complete in %.2f seconds", elapsed)
            logger.info("  ColorAgent: %d seconds analyzed", len(visual_timeline))
            logger.info("  AudioAgent: %d seconds analyzed", len(audio_timeline))
            
            visual_done = True
            audio_done = True
            
        except Exception as exc:
            logger.exception("Parallel analysis failed: %s", exc)
        
        # Return combined results
        return {
            "visual_timeline": visual_timeline,
            "audio_timeline": audio_timeline,
            "visual_timeline_done": visual_done,
            "audio_timeline_done": audio_done,
        }
    
    return parallel_analysis_node


def make_color_full_video_node(
    registry: Any,
    timeline_state: Any,
    sse_manager: Any
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for full-video color analysis node."""
    
    async def color_full_video_node(state: AgentState) -> AgentState:
        """Analyze entire video per-second for visual features."""
        project_id = state["project_id"]
        logger.info("🎨 ColorAgent: Analyzing full video per-second for project %s", project_id)
        
        try:
            color_agent = registry.get_agent("color.analyze")
            if color_agent is None:
                raise ValueError("ColorAgent not found in registry")
            
            # Run full video analysis
            visual_timeline = await color_agent.analyze_full_video()
            
            logger.info("✓ ColorAgent: Analyzed %d seconds", len(visual_timeline))
            
            # Return ONLY color-specific keys
            return {
                "visual_timeline": visual_timeline,
                "visual_timeline_done": True
            }
            
        except Exception as exc:
            logger.exception("Full video color analysis failed: %s", exc)
            # Return ONLY color-specific keys even on error
            return {
                "visual_timeline": [],
                "visual_timeline_done": False,
            }
    
    return color_full_video_node


def make_audio_full_video_node(
    registry: Any,
    timeline_state: Any,
    sse_manager: Any
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for full-video audio analysis node."""
    
    async def audio_full_video_node(state: AgentState) -> AgentState:
        """Analyze entire video per-second for audio features."""
        project_id = state["project_id"]
        logger.info("🎵 AudioAgent: Analyzing full video per-second for project %s", project_id)
        
        try:
            audio_agent = registry.get_agent("audio.analyze")
            if audio_agent is None:
                raise ValueError("AudioAgent not found in registry")
            
            # Run full video analysis
            audio_timeline = await audio_agent.analyze_full_video()
            
            logger.info("✓ AudioAgent: Analyzed %d seconds", len(audio_timeline))
            
            # Return ONLY audio-specific keys
            return {
                "audio_timeline": audio_timeline,
                "audio_timeline_done": True
            }
            
        except Exception as exc:
            logger.exception("Full video audio analysis failed: %s", exc)
            # Return ONLY audio-specific keys even on error
            return {
                "audio_timeline": [],
                "audio_timeline_done": False,
            }
    
    return audio_full_video_node


def make_reassembly_node(
    registry: Any,
    timeline_state: Any,
    config: dict
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function for reassembly node."""
    
    async def reassembly_node(state: AgentState) -> AgentState:
        """
        Attach per-second features to existing segments.
        
        NOTE: Segments (including silent) already exist from transcription phase.
        We only need to map features to segments and batch save.
        """
        import numpy as np
        
        project_id = state["project_id"]
        logger.info("🔧 Reassembly: Attaching features to %d segments", 
                   timeline_state.segment_count())
        
        try:
            # Get all existing segments (includes speech + silent)
            all_segments = list(timeline_state.get_all_segments().values())
            visual_timeline = state.get("visual_timeline", [])
            audio_timeline = state.get("audio_timeline", [])
            
            logger.info("Mapping features: %d segments, %d visual, %d audio samples",
                       len(all_segments), len(visual_timeline), len(audio_timeline))
            
            # Build feature maps by segment ID
            visual_features_map = {}
            audio_features_map = {}
            
            for seg in all_segments:
                # Extract time range for this segment
                start_idx = int(seg.start)
                end_idx = int(np.ceil(seg.end))
                
                # Slice per-second timelines to match segment range
                visual_features_map[seg.id] = [
                    v for v in visual_timeline
                    if start_idx <= v.get("time", 0) < end_idx
                ]
                
                audio_features_map[seg.id] = [
                    a for a in audio_timeline
                    if start_idx <= a.get("time", 0) < end_idx
                ]
            
            # Batch save all features (single file write per agent)
            timeline_state.set_layers_batch("color_agent", visual_features_map)
            timeline_state.set_layers_batch("audio_agent", audio_features_map)
            
            logger.info("✓ Reassembly complete: features attached to %d segments", 
                       len(all_segments))
            
            return {
                **state,
                "phase": "complete",
                "success": True,
                "summary": f"Features attached to {len(all_segments)} segments"
            }
            
        except Exception as exc:
            logger.exception("Reassembly failed: %s", exc)
            return {
                **state,
                "phase": "complete",
                "success": False,
                "error": str(exc)
            }
    
    return reassembly_node


def make_error_handler_node(
    timeline_state: Any,
    sse_manager: Any
) -> Callable[[AgentState], Awaitable[AgentState]]:
    """Factory function that creates error handler node with captured dependencies."""
    
    async def error_handler_node(state: AgentState) -> AgentState:
        """
        Handle errors and perform rollback if needed.
        
        Called when agents fail during execution.
        """
        project_id = state["project_id"]
        error = state.get("error", "Unknown error")
        
        logger.error("Error handler invoked for project %s: %s", project_id, error)
        
        # Perform rollback if snapshot exists
        snapshot_id = state.get("snapshot_id")
        if snapshot_id:
            logger.info("Rolling back to snapshot %s", snapshot_id)
            timeline_state.rollback(snapshot_id)
        
        # Send error event
        sse_event = SSEEvent(
            event="error",
            data={"error": error, "message": f"Processing failed: {error}"},
            checkpoint_id=state.get("last_checkpoint")
        )
        sse_manager.add_event(project_id, sse_event)
        
        return {
            **state,
            "success": False,
            "error": error
        }
    
    return error_handler_node
