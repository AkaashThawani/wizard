"""
orchestrator/sse_manager.py

SSE Connection Manager with checkpoint-based reconnection support.

Manages Server-Sent Events (SSE) connections, event caching, and replay
for seamless reconnection when backend restarts or network interrupts.
"""

import time
import logging
from typing import Dict, List
from orchestrator.graph_types import SSEEvent, CheckpointMetadata

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """
    Manages SSE connections with checkpointing for reconnection.
    
    Features:
    - Caches recent events per project (last 100)
    - Tracks checkpoint IDs for resumption points
    - Replays events on reconnection
    - Auto-cleanup of old data
    """
    
    def __init__(self, max_events_per_project: int = 100):
        self._project_events: Dict[str, List[dict]] = {}
        self._project_checkpoints: Dict[str, CheckpointMetadata] = {}
        self._max_events = max_events_per_project
    
    def add_event(self, project_id: str, event: SSEEvent) -> None:
        """
        Store event for potential replay on reconnection.
        
        Args:
            project_id: Project identifier
            event: SSE event to store
        """
        if project_id not in self._project_events:
            self._project_events[project_id] = []
        
        # Convert to dict with timestamp
        event_dict = event.to_json()
        event_dict["timestamp"] = time.time()
        
        self._project_events[project_id].append(event_dict)
        
        # Keep only last N events
        if len(self._project_events[project_id]) > self._max_events:
            self._project_events[project_id].pop(0)
        
        logger.debug(
            "SSE event cached for project %s: %s (checkpoint: %s)",
            project_id, event.event, event.checkpoint_id
        )
    
    def set_checkpoint(self, project_id: str, checkpoint: CheckpointMetadata) -> None:
        """Store checkpoint metadata for project."""
        self._project_checkpoints[project_id] = checkpoint
        logger.info(
            "Checkpoint saved for project %s: %s (phase: %s)",
            project_id, checkpoint.checkpoint_id, checkpoint.phase
        )
    
    def get_checkpoint(self, project_id: str) -> CheckpointMetadata | None:
        """Get last checkpoint for project."""
        return self._project_checkpoints.get(project_id)
    
    def get_events_since(self, project_id: str, checkpoint_id: str | None) -> List[dict]:
        """
        Get all events after specified checkpoint for replay.
        
        Args:
            project_id: Project identifier
            checkpoint_id: Last checkpoint received by client (None = send all)
        
        Returns:
            List of events to replay
        """
        events = self._project_events.get(project_id, [])
        
        if checkpoint_id is None:
            # Send all events
            logger.info("Replaying all %d events for project %s", len(events), project_id)
            return events
        
        # Find checkpoint position
        checkpoint_idx = -1
        for i, event in enumerate(events):
            if event.get("checkpoint_id") == checkpoint_id:
                checkpoint_idx = i
                break
        
        # Return events after checkpoint
        if checkpoint_idx >= 0:
            replay_events = events[checkpoint_idx + 1:]
            logger.info(
                "Replaying %d events since checkpoint %s for project %s",
                len(replay_events), checkpoint_id, project_id
            )
            return replay_events
        
        # Checkpoint not found - send all (safer than sending none)
        logger.warning(
            "Checkpoint %s not found for project %s, replaying all %d events",
            checkpoint_id, project_id, len(events)
        )
        return events
    
    def cleanup_project(self, project_id: str) -> None:
        """Remove all data for a project."""
        self._project_events.pop(project_id, None)
        self._project_checkpoints.pop(project_id, None)
        logger.info("Cleaned up SSE data for project %s", project_id)
    
    def cleanup_old_projects(self, max_age_seconds: float = 3600) -> None:
        """
        Remove data for projects with no recent activity.
        
        Args:
            max_age_seconds: Remove projects inactive for this long (default: 1 hour)
        """
        now = time.time()
        projects_to_remove = []
        
        for project_id, events in self._project_events.items():
            if not events:
                projects_to_remove.append(project_id)
                continue
            
            last_event_time = events[-1].get("timestamp", 0)
            if now - last_event_time > max_age_seconds:
                projects_to_remove.append(project_id)
        
        for project_id in projects_to_remove:
            self.cleanup_project(project_id)
        
        if projects_to_remove:
            logger.info("Cleaned up %d inactive projects", len(projects_to_remove))
