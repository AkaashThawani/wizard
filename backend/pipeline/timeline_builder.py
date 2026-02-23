"""
pipeline/timeline_builder.py

Builds complete timeline including silent segments and attaches
per-second visual/audio features to each segment.

This runs after:
1. TranscriptionAgent produces speech segments
2. ColorAgent analyzes full video per-second
3. AudioAgent analyzes full video per-second
"""

from __future__ import annotations

import uuid
import logging
from typing import Any
import numpy as np
from timeline.models import Segment

logger = logging.getLogger(__name__)


def fill_silent_gaps(
    speech_segments: list[Segment],
    video_duration: float,
    min_silence_duration: float = 0.5
) -> list[Segment]:
    """
    Create complete segment list including silent gaps.
    
    Returns chronologically ordered list of all segments (speech + silent).
    Silent segments have is_silent=True and empty text.
    
    Called immediately after transcription, BEFORE feature analysis.
    Features are attached later by reassembly_node.
    
    Args:
        speech_segments: Segments from transcription pipeline
        video_duration: Total video duration in seconds
        min_silence_duration: Minimum silence gap to create a segment
    
    Returns:
        Complete segment list (speech + silent) in chronological order
    """
    timeline = []
    current_time = 0.0
    source = speech_segments[0].source if speech_segments else ""
    
    # Sort speech segments by start time
    sorted_segments = sorted(speech_segments, key=lambda s: s.start)
    
    for seg in sorted_segments:
        # Check for silence gap before this speech segment
        gap_duration = seg.start - current_time
        
        if gap_duration >= min_silence_duration:
            # Create silent segment
            silent_seg = Segment(
                id=f"silent_{uuid.uuid4().hex[:8]}",
                start=current_time,
                end=seg.start,
                duration=gap_duration,
                text="",
                words=[],
                speaker=None,
                source=source,
                chroma_id="",
                is_silent=True
            )
            timeline.append(silent_seg)
        
        # Add speech segment
        timeline.append(seg)
        current_time = seg.end
    
    # Handle trailing silence
    trailing_duration = video_duration - current_time
    if trailing_duration >= min_silence_duration:
        silent_seg = Segment(
            id=f"silent_{uuid.uuid4().hex[:8]}",
            start=current_time,
            end=video_duration,
            duration=trailing_duration,
            text="",
            words=[],
            speaker=None,
            source=source,
            chroma_id="",
            is_silent=True
        )
        timeline.append(silent_seg)
    
    logger.info("✓ Created complete timeline: %d speech + %d silent segments",
               sum(1 for s in timeline if not s.is_silent),
               sum(1 for s in timeline if s.is_silent))
    
    return timeline


def build_complete_timeline(
    speech_segments: list[Segment],
    video_duration: float,
    visual_timeline: list[dict],
    audio_timeline: list[dict],
    min_silence_duration: float = 0.5
) -> tuple[list[Segment], dict[str, list[dict]], dict[str, list[dict]]]:
    """
    Create complete timeline with silent segments and per-second features.
    
    Args:
        speech_segments: Segments from TranscriptionAgent
        video_duration: Total video duration in seconds
        visual_timeline: Per-second visual analysis from ColorAgent
        audio_timeline: Per-second audio analysis from AudioAgent
        min_silence_duration: Minimum silence gap to create a segment
    
    Returns:
        Tuple of (segments, visual_features_map, audio_features_map)
        - segments: Complete timeline with speech + silent segments
        - visual_features_map: {segment_id: [per-second visual data]}
        - audio_features_map: {segment_id: [per-second audio data]}
    """
    timeline = []
    visual_features_map = {}
    audio_features_map = {}
    current_time = 0.0
    
    # Sort speech segments by start time
    sorted_segments = sorted(speech_segments, key=lambda s: s.start)
    
    for seg in sorted_segments:
        # Check for silence gap before this speech segment
        gap_duration = seg.start - current_time
        
        if gap_duration >= min_silence_duration:
            # Create silent segment
            silent_seg = Segment(
                id=f"silent_{uuid.uuid4().hex[:8]}",
                start=current_time,
                end=seg.start,
                duration=gap_duration,
                text="",  # No transcription
                words=[],
                speaker=None,
                source=seg.source,
                chroma_id="",
                is_silent=True
            )
            
            # Extract and store features for silent segment
            visual_feats, audio_feats = _extract_features(silent_seg, visual_timeline, audio_timeline)
            visual_features_map[silent_seg.id] = visual_feats
            audio_features_map[silent_seg.id] = audio_feats
            timeline.append(silent_seg)
            
            logger.debug("Added silent segment: %.2fs - %.2fs (%.2fs)", 
                        current_time, seg.start, gap_duration)
        
        # Extract and store features for speech segment
        visual_feats, audio_feats = _extract_features(seg, visual_timeline, audio_timeline)
        visual_features_map[seg.id] = visual_feats
        audio_features_map[seg.id] = audio_feats
        timeline.append(seg)
        
        current_time = seg.end
    
    # Handle trailing silence
    trailing_duration = video_duration - current_time
    if trailing_duration >= min_silence_duration:
        silent_seg = Segment(
            id=f"silent_{uuid.uuid4().hex[:8]}",
            start=current_time,
            end=video_duration,
            duration=trailing_duration,
            text="",
            words=[],
            speaker=None,
            source=sorted_segments[0].source if sorted_segments else "",
            chroma_id="",
            is_silent=True
        )
        
        # Extract and store features for trailing silence
        visual_feats, audio_feats = _extract_features(silent_seg, visual_timeline, audio_timeline)
        visual_features_map[silent_seg.id] = visual_feats
        audio_features_map[silent_seg.id] = audio_feats
        timeline.append(silent_seg)
        
        logger.debug("Added trailing silent segment: %.2fs - %.2fs (%.2fs)", 
                    current_time, video_duration, trailing_duration)
    
    logger.info("✓ Built complete timeline: %d segments (%d speech, %d silent)",
               len(timeline),
               sum(1 for s in timeline if not s.is_silent),
               sum(1 for s in timeline if s.is_silent))
    
    return timeline, visual_features_map, audio_features_map


def _extract_features(
    segment: Segment,
    visual_timeline: list[dict],
    audio_timeline: list[dict]
) -> tuple[list[dict], list[dict]]:
    """
    Extract per-second features for segment's duration.
    
    Returns features that match the segment's time range.
    
    Returns:
        (visual_features, audio_features) - Lists of per-second feature dicts
    """
    # Extract time range for this segment
    start_idx = int(segment.start)
    end_idx = int(np.ceil(segment.end))
    
    # Slice visual timeline
    segment_visual = [
        v for v in visual_timeline
        if start_idx <= v.get("time", 0) < end_idx
    ]
    
    # Slice audio timeline
    segment_audio = [
        a for a in audio_timeline
        if start_idx <= a.get("time", 0) < end_idx
    ]
    
    logger.debug("Extracted features for %s: %d visual, %d audio samples",
                segment.id, len(segment_visual), len(segment_audio))
    
    return segment_visual, segment_audio
