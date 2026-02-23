"""
agents/audio_agent.py

AudioAgent — audio feature analysis using librosa.

Extracts audio features from video segments for audio-based search
and analysis capabilities.

Tool: audio.analyze {segment_ids: list[str]}
"""

from __future__ import annotations

import logging
import os
import tempfile
import numpy as np

from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Re-enable INFO for debugging

# Sample rate for audio analysis
SAMPLE_RATE = 22050


class AudioAgent(BaseAgent):
    """
    Audio feature analysis agent using librosa.
    
    Capabilities:
    - Extract audio features: energy (RMS), pitch, speech rate
    - Generate audio feature vectors for similarity search
    - Store features in ChromaDB chroma/audio collection
    - Enable audio-based queries ("high energy moments", "fast speech")
    """

    def description(self) -> str:
        return "Analyses audio features of segments using librosa for audio search."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="audio.analyze",
                description=(
                    "Analyse audio features of specified segments. "
                    "Extracts energy, pitch, and speech rate features stored in "
                    "chroma/audio for audio similarity search."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Segment IDs to analyse. Analyses all segments if omitted.",
                        }
                    },
                    "required": [],
                },
            ),
            Tool(
                name="audio.reanalyze_segment",
                description=(
                    "Re-analyze audio features of a specific segment. "
                    "Useful after edits (trim, effects) to get updated audio analysis. "
                    "Uses current effective segment state (with edits applied)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "segment_id": {
                            "type": "string",
                            "description": "Segment ID to reanalyze.",
                        }
                    },
                    "required": ["segment_id"],
                },
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("audio.analyze", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def analyze_full_video(self) -> list[dict]:
        """
        Analyze entire video audio per-second in parallel.
        
        Returns:
            List of dicts, one per second:
            [
                {"time": 0.0, "energy_rms": 0.02, "pitch_hz": 832, "spectral_centroid": 1975, ...},
                {"time": 1.0, "energy_rms": 0.03, "pitch_hz": 850, "spectral_centroid": 2010, ...},
                ...
            ]
        """
        import concurrent.futures
        
        source_path = self.state.source_path
        video_duration = self.state.video_duration
        
        if not source_path or not os.path.exists(source_path):
            logger.warning("Source video not found: %s", source_path)
            return []
        
        num_seconds = int(np.ceil(video_duration))
        logger.info("AudioAgent analyzing %d seconds in parallel...", num_seconds)
        
        # Analyze all seconds in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._analyze_single_second, source_path, t, min(t+1, video_duration)): t
                for t in range(num_seconds)
            }
            
            results = {}
            for future in concurrent.futures.as_completed(futures):
                t = futures[future]
                try:
                    results[t] = future.result()
                except Exception as exc:
                    logger.error("Failed to analyze second %d: %s", t, exc)
                    # Placeholder
                    results[t] = {
                        "time": float(t),
                        "energy_rms": 0.0,
                        "energy_max": 0.0,
                        "energy_std": 0.0,
                        "pitch_hz": 0.0,
                        "pitch_std": 0.0,
                        "spectral_centroid": 0.0,
                        "spectral_rolloff": 0.0,
                        "zero_crossing_rate": 0.0,
                        "speech_rate_wps": 0.0
                    }
        
        timeline = [results[t] for t in sorted(results.keys())]
        logger.info("✓ AudioAgent analyzed %d seconds", len(timeline))
        return timeline

    def _analyze_single_second(self, video_path: str, start_time: float, end_time: float) -> dict:
        """Analyze 1-second audio window."""
        features = self._extract_audio_features(video_path, start_time, end_time, f"sec_{int(start_time)}")
        
        if features:
            features["time"] = start_time
            return features
        else:
            return {
                "time": start_time,
                "energy_rms": 0.0,
                "energy_max": 0.0,
                "energy_std": 0.0,
                "pitch_hz": 0.0,
                "pitch_std": 0.0,
                "spectral_centroid": 0.0,
                "spectral_rolloff": 0.0,
                "zero_crossing_rate": 0.0,
                "speech_rate_wps": 0.0
            }

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name == "audio.reanalyze_segment":
            return await self._reanalyze_segment_tool(params)
        
        if name != "audio.analyze":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        try:
            segment_ids = params.get("segment_ids") or list(self.state.get_all_segments().keys())
            
            if not segment_ids:
                return ToolResult(
                    success=True,
                    data={"segments_processed": 0, "message": "No segments to analyze"},
                )
            
            logger.info("AudioAgent analyzing %d segments...", len(segment_ids))
            
            # Process each segment
            processed = 0
            errors = []
            
            for seg_id in segment_ids:
                try:
                    result = await self._analyze_segment(seg_id)
                    if result:
                        processed += 1
                except Exception as e:
                    logger.error("Failed to analyze segment %s: %s", seg_id, e)
                    errors.append({"segment_id": seg_id, "error": str(e)})
            
            logger.info("✓ AudioAgent processed %d/%d segments", processed, len(segment_ids))
            
            return ToolResult(
                success=True,
                data={
                    "segments_processed": processed,
                    "segments_total": len(segment_ids),
                    "errors": errors if errors else None,
                },
            )
            
        except Exception as exc:
            logger.exception("AudioAgent analysis failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _analyze_segment(self, segment_id: str) -> dict | None:
        """Analyze a single segment with librosa."""
        segment = self.state.get_effective_segment(segment_id)
        if not segment:
            logger.warning("Segment %s not found", segment_id)
            return None
        
        source_path = self.state.source_path
        if not source_path or not os.path.exists(source_path):
            logger.warning("Source video not found: %s", source_path)
            return None
        
        # Extract audio features
        features = self._extract_audio_features(source_path, segment.start, segment.end, segment_id)
        
        if not features:
            return None
        
        # Store in state layers
        self.state.set_layer("audio_agent", segment_id, features)
        logger.info("✓ AudioAgent: Stored features for %s - energy=%.3f, pitch=%.1fHz, rate=%.1fwps",
                   segment_id, features["energy_rms"], features["pitch_hz"], features["speech_rate_wps"])
        
        # Store in ChromaDB
        self._store_in_chromadb(segment_id, features)
        
        return features
    
    def _extract_audio_features(self, video_path: str, start_time: float, end_time: float, segment_id: str) -> dict | None:
        """Extract audio features using librosa."""
        try:
            import librosa
            import soundfile as sf
            import subprocess
            
            # Calculate duration
            duration = end_time - start_time
            if duration <= 0:
                logger.warning("Invalid segment duration: %.2f", duration)
                return None
            
            # Extract audio segment using FFmpeg
            temp_dir = tempfile.gettempdir()
            audio_path = os.path.join(temp_dir, f"audio_{segment_id}.wav")
            
            # FFmpeg command to extract audio segment
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-ss", str(start_time),  # Start time
                "-t", str(duration),  # Duration
                "-i", video_path,  # Input
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM audio
                "-ar", str(SAMPLE_RATE),  # Sample rate
                "-ac", "1",  # Mono
                audio_path,
                "-loglevel", "error"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("FFmpeg error: %s", result.stderr)
                return None
            
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                logger.warning("Empty audio file for segment %s", segment_id)
                return None
            
            try:
                # Load audio with librosa
                y, sr = librosa.load(audio_path, sr=SAMPLE_RATE)
                
                if len(y) == 0:
                    logger.warning("No audio data for segment %s", segment_id)
                    return None
                
                # Extract features
                features = {}
                
                # 1. Energy (RMS)
                rms = librosa.feature.rms(y=y)[0]
                features["energy_rms"] = float(np.mean(rms))
                features["energy_max"] = float(np.max(rms))
                features["energy_std"] = float(np.std(rms))
                
                # 2. Pitch (fundamental frequency)
                try:
                    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
                    # Get pitch with highest magnitude at each frame
                    pitch_values = []
                    for t in range(pitches.shape[1]):
                        index = magnitudes[:, t].argmax()
                        pitch = pitches[index, t]
                        if pitch > 0:  # Valid pitch
                            pitch_values.append(pitch)
                    
                    if pitch_values:
                        features["pitch_hz"] = float(np.median(pitch_values))
                        features["pitch_std"] = float(np.std(pitch_values))
                    else:
                        features["pitch_hz"] = 0.0
                        features["pitch_std"] = 0.0
                except Exception as e:
                    logger.debug("Pitch extraction failed: %s", e)
                    features["pitch_hz"] = 0.0
                    features["pitch_std"] = 0.0
                
                # 3. Speech rate (words per second)
                segment = self.state.get_effective_segment(segment_id)
                if segment and segment.text:
                    word_count = len(segment.text.split())
                    features["speech_rate_wps"] = float(word_count / duration)
                else:
                    features["speech_rate_wps"] = 0.0
                
                # 4. Spectral features
                spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
                features["spectral_centroid"] = float(np.mean(spectral_centroids))
                
                spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
                features["spectral_rolloff"] = float(np.mean(spectral_rolloff))
                
                # 5. Zero crossing rate (indicates percussiveness)
                zcr = librosa.feature.zero_crossing_rate(y)[0]
                features["zero_crossing_rate"] = float(np.mean(zcr))
                
                # 6. Create feature vector for embedding
                feature_vector = [
                    features["energy_rms"],
                    features["energy_std"],
                    features["pitch_hz"] / 1000.0,  # Normalize
                    features["pitch_std"] / 1000.0,
                    features["speech_rate_wps"] / 10.0,  # Normalize
                    features["spectral_centroid"] / 10000.0,  # Normalize
                    features["spectral_rolloff"] / 10000.0,
                    features["zero_crossing_rate"],
                ]
                features["audio_embedding"] = feature_vector
                
                return features
                
            finally:
                # Clean up temp audio file
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.error("Audio feature extraction error: %s", e)
            return None
    
    def _store_in_chromadb(self, segment_id: str, features: dict):
        """Store audio features in ChromaDB."""
        try:
            import chromadb
            import logging as log_module
            from utils.suppress_output import safe_embedding
            
            # Suppress ChromaDB verbose output
            log_module.getLogger("chromadb").setLevel(log_module.ERROR)
            
            # Get or create ChromaDB client
            project_dir = os.path.dirname(self.state.source_path) if self.state.source_path else "."
            chroma_dir = os.path.join(project_dir, "chroma")
            os.makedirs(chroma_dir, exist_ok=True)
            
            client = chromadb.PersistentClient(path=chroma_dir)
            collection = client.get_or_create_collection(name="audio")
            
            # Add embedding
            segment = self.state.get_effective_segment(segment_id)
            metadata = {
                "segment_id": segment_id,
                "start": segment.start,
                "end": segment.end,
                "energy_rms": features["energy_rms"],
                "pitch_hz": features["pitch_hz"],
                "speech_rate_wps": features["speech_rate_wps"],
            }
            
            # Ensure embedding is pure Python list to prevent ChromaDB debug output
            collection.add(
                embeddings=[safe_embedding(features["audio_embedding"])],
                documents=[segment.text or ""],
                metadatas=[metadata],
                ids=[segment_id]
            )
            
            logger.debug("Stored audio features for segment %s", segment_id)
            
        except Exception as e:
            logger.error("Failed to store in ChromaDB: %s", e)

    async def _reanalyze_segment_tool(self, params: dict) -> ToolResult:
        """Tool handler for segment reanalysis."""
        segment_id = params.get("segment_id")
        
        if not segment_id:
            return ToolResult(
                success=False,
                data={},
                error="segment_id parameter is required"
            )
        
        try:
            logger.info("AudioAgent re-analyzing segment %s (with current edits)...", segment_id)
            
            result = await self._analyze_segment(segment_id)
            
            if not result:
                return ToolResult(
                    success=False,
                    data={},
                    error=f"Failed to analyze segment {segment_id}"
                )
            
            return ToolResult(
                success=True,
                data={
                    "segment_id": segment_id,
                    "analysis": {
                        "energy_rms": result["energy_rms"],
                        "pitch_hz": result["pitch_hz"],
                        "speech_rate_wps": result["speech_rate_wps"],
                        "spectral_centroid": result["spectral_centroid"],
                    },
                    "message": f"Re-analyzed segment {segment_id} with current edits applied"
                },
            )
            
        except Exception as exc:
            logger.exception("AudioAgent reanalysis failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    def get_lean_context(self) -> dict:
        layer = self.state.get_agent_layer("audio_agent")
        return {
            "segments_analysed": len(layer),
            "audio_search_enabled": len(layer) > 0,
        }
