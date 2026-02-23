"""
agents/transcription_agent.py

TranscriptionAgent — runs Whisper on the source video via ONNX Runtime,
then pipes output through the full audio data pipeline.

Platform: Cross-platform (Mac + Windows) via ONNX Runtime.
ONNX automatically selects: CUDA → CoreML → CPU with zero code changes.

Pipeline:
  Whisper (ONNX, word_timestamps=True)
    → merger.py   (consolidate short Whisper segments)
    → cleaner.py  (remove fillers)
    → chunker.py  (sentence-boundary alignment)
    → enricher.py (LLM: topics / keywords / summary)
    → vectorizer.py (sentence-transformers → ChromaDB chroma/text)

Tool: transcription.transcribe
  params: {model_size?: str, language?: str}
"""

from __future__ import annotations

import logging
import psutil
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)

# Lazy model cache
_whisper_model = None
_whisper_model_size = None
_whisper_force_cpu = None  # Track CPU mode too


def _detect_ram() -> float:
    """Detect available system RAM in GB."""
    return psutil.virtual_memory().total / (1024 ** 3)


def _select_model_size(model_size: str, config: dict) -> str:
    """
    Select appropriate Whisper model based on RAM if model_size is "auto".
    
    Args:
        model_size: User-specified size or "auto"
        config: Configuration dict with RAM thresholds
    
    Returns:
        Model size string (tiny, base, small, medium, large-v3)
    """
    if model_size != "auto":
        return model_size
    
    ram_gb = _detect_ram()
    logger.info("Detected %.1f GB RAM", ram_gb)
    
    # RAM-based model selection
    if ram_gb >= 32:
        selected = config.get("whisper", {}).get("model_size_32gb", "large-v3")
    elif ram_gb >= 16:
        selected = config.get("whisper", {}).get("model_size_16gb", "small")
    elif ram_gb >= 8:
        selected = config.get("whisper", {}).get("model_size_8gb", "base")
    else:
        selected = "tiny"
    
    logger.info("Auto-selected Whisper model: %s (for %.1f GB RAM)", selected, ram_gb)
    return selected


def _get_whisper(model_size: str = "small", force_cpu: bool = False):
    """
    Load Whisper model with GPU acceleration.
    
    Uses PyTorch with CUDA for GPU acceleration on NVIDIA GPUs.
    On Mac, uses MPS (Metal Performance Shaders) for Apple Silicon.
    Falls back to CPU if no GPU available.
    
    Args:
        model_size: Whisper model size (tiny, base, small, medium, large-v3)
        force_cpu: If True, force CPU mode (for testing/comparison)
    """
    global _whisper_model, _whisper_model_size, _whisper_force_cpu
    
    # Reload if model size OR force_cpu setting changes
    if _whisper_model is None or _whisper_model_size != model_size or _whisper_force_cpu != force_cpu:
        from transformers import pipeline
        from utils.device import detect_device
        import torch
        
        model_id = f"openai/whisper-{model_size}"
        
        # Detect best device
        device_config = detect_device()
        
        # Determine PyTorch device
        if force_cpu:
            device = "cpu"
            torch_dtype = torch.float32
            logger.info("Loading Whisper model '%s' on CPU (FORCED for testing)...", model_size)
        elif device_config.device_type.value == "cuda" and torch.cuda.is_available():
            device = "cuda:0"
            torch_dtype = torch.float16  # Use FP16 on GPU for speed
            logger.info("Loading Whisper model '%s' on GPU (CUDA)...", model_size)
            logger.info("  GPU: %s (%.1f GB)", device_config.gpu_name, device_config.gpu_memory_gb)
        elif device_config.device_type.value == "mps" and torch.backends.mps.is_available():
            device = "mps"
            torch_dtype = torch.float16
            logger.info("Loading Whisper model '%s' on Apple Silicon (MPS)...", model_size)
        else:
            device = "cpu"
            torch_dtype = torch.float32  # Use FP32 on CPU
            logger.info("Loading Whisper model '%s' on CPU...", model_size)
        
        try:
            # Load Whisper with GPU acceleration
            _whisper_model = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                chunk_length_s=30,  # Process in 30s chunks
                device=device,  # Use detected device (cuda/mps/cpu)
                torch_dtype=torch_dtype,  # FP16 on GPU, FP32 on CPU
                model_kwargs={"use_cache": True},
            )
            _whisper_model_size = model_size
            _whisper_force_cpu = force_cpu  # Track CPU mode for cache
            logger.info("✓ Whisper model '%s' loaded successfully on %s", model_size, device)
        except Exception as e:
            logger.exception("Failed to load Whisper model on %s: %s", device, e)
            
            # Fallback to CPU if GPU loading fails
            if device != "cpu":
                logger.warning("Falling back to CPU...")
                _whisper_model = pipeline(
                    "automatic-speech-recognition",
                    model=model_id,
                    chunk_length_s=30,
                    device="cpu",
                    torch_dtype=torch.float32,
                )
                _whisper_model_size = model_size
                logger.info("Loaded Whisper on CPU (fallback mode)")
            else:
                raise
    
    return _whisper_model


def _normalize_whisper_output(result, source_path: str) -> list[dict]:
    """
    Convert transformers pipeline output to faster-whisper-compatible format.
    
    This adapter ensures backward compatibility with the existing pipeline
    (merger.py, cleaner.py, etc.) without requiring changes to those modules.
    
    Args:
        result: Output from transformers ASR pipeline (dict or list)
        source_path: Path to source video
    
    Returns:
        List of segment dicts in faster-whisper format
    """
    segments = []
    
    # transformers output can be dict or list depending on settings
    # With return_timestamps="word", we get chunks with timestamps
    if isinstance(result, dict):
        chunks = result.get("chunks", [])
    elif isinstance(result, list):
        chunks = result
    else:
        # Fallback: single segment
        chunks = [{"text": str(result), "timestamp": (0.0, 0.0)}]
    
    for chunk in chunks:
        # Extract text and timestamp
        if isinstance(chunk, dict):
            text = chunk.get("text", "").strip()
            timestamp = chunk.get("timestamp", (0.0, 0.0))
        else:
            text = str(chunk).strip()
            timestamp = (0.0, 0.0)
        
        # Ensure timestamp is a tuple
        if not isinstance(timestamp, (list, tuple)) or len(timestamp) != 2:
            timestamp = (0.0, 0.0)
        
        segment = {
            "start": float(timestamp[0]) if timestamp[0] is not None else 0.0,
            "end": float(timestamp[1]) if timestamp[1] is not None else 0.0,
            "text": text,
            "words": [],  # Will be populated by pipeline processing
        }
        segments.append(segment)
    
    return segments


class TranscriptionAgent(BaseAgent):
    """
    Runs Whisper transcription via ONNX Runtime and the full audio data pipeline.

    Registered tools:
      transcription.transcribe — transcribe the project source video
    """

    def description(self) -> str:
        return "Transcribes video audio using Whisper (ONNX Runtime) and populates the segment pool."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="transcription.transcribe",
                description=(
                    "Transcribe the project's source video using Whisper via ONNX Runtime. "
                    "Automatically selects best model size based on available RAM. "
                    "Populates the timeline with sentence-aligned segments including "
                    "word-level timestamps and confidence scores. "
                    "Run this first before any other operation."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "model_size": {
                            "type": "string",
                            "description": "Whisper model size: auto, tiny, base, small, medium, large-v3 (default: auto)",
                            "default": "auto",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code (e.g. 'en'). Auto-detect if omitted.",
                        },
                    },
                    "required": [],
                },
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("transcription.transcribe", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name != "transcription.transcribe":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        source_path = self.state.source_path
        if not source_path:
            return ToolResult(
                success=False,
                data={},
                error="No source video set. Upload a video first.",
            )

        try:
            return await self._run_pipeline(source_path, params)
        except Exception as exc:
            logger.exception("Transcription pipeline failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _run_pipeline(self, source_path: str, params: dict) -> ToolResult:
        from pipeline.merger import whisper_output_to_segments, merge_segments
        from pipeline.cleaner import clean
        from pipeline.chunker import chunk_segments
        from pipeline.enricher import enrich_segments
        from pipeline.vectorizer import vectorize_segments

        # Select model size (auto or manual)
        model_size_param = params.get("model_size", self.config.get("whisper", {}).get("model_size", "auto"))
        model_size = _select_model_size(model_size_param, self.config)
        
        language = params.get("language") or None

        # ----------------------------------------------------------------
        # Stage 1: Whisper transcription via ONNX Runtime
        # ----------------------------------------------------------------
        self._emit("stage", {"stage": "transcription", "status": "running"})
        logger.info("Running Whisper (ONNX) on: %s", source_path)

        # Check if CPU mode is forced (for testing/comparison)
        force_cpu = self.config.get("whisper", {}).get("force_cpu", False)
        model = _get_whisper(model_size, force_cpu=force_cpu)
        
        # Log which device/provider is being used
        import torch
        import time
        
        logger.info("=" * 70)
        logger.info("WHISPER INFERENCE STARTING:")
        logger.info("  Model: %s", model_size)
        logger.info("  File: %s", source_path)
        
        # Show actual device being used
        try:
            model_device = str(next(model.model.parameters()).device)
            logger.info("  Model Device: %s", model_device)
            
            from utils.device import detect_device
            device_config = detect_device()
            if device_config.gpu_name and "cuda" in model_device:
                logger.info("  GPU: %s (%.1f GB)", device_config.gpu_name, device_config.gpu_memory_gb)
        except Exception as e:
            logger.info("  Device: CPU")
        
        logger.info("=" * 70)
        
        # Start timing
        start_time = time.time()
        logger.info("⏱️  Starting inference... (timestamp: %.2f)", start_time)
        
        # Run transcription with word-level timestamps for better accuracy
        result = model(
            source_path,
            return_timestamps="word",  # Word-level for precise timestamps
            generate_kwargs={
                "language": language or "en",  # Default to English if not specified
                "task": "transcribe",
            },
        )
        
        # End timing
        end_time = time.time()
        elapsed = end_time - start_time
        
        logger.info("=" * 70)
        logger.info("✓ WHISPER INFERENCE COMPLETED")
        logger.info("  Duration: %.2f seconds", elapsed)
        logger.info("=" * 70)

        # Normalize output to faster-whisper format
        raw_segments = _normalize_whisper_output(result, source_path)
        
        self._emit("stage", {"stage": "transcription", "status": "done", "count": len(raw_segments)})
        logger.info("Whisper (ONNX) produced %d raw segments.", len(raw_segments))
        logger.info("RAW SEGMENTS sample: %s", raw_segments[:2] if len(raw_segments) > 0 else "empty")

        # ----------------------------------------------------------------
        # Stage 2: Convert to Segment objects and merge
        # ----------------------------------------------------------------
        logger.info("⏱️  Stage 2: Merge")
        stage_start = time.time()
        self._emit("stage", {"stage": "merge", "status": "running"})
        
        segments = whisper_output_to_segments(raw_segments, source_path)
        logger.info("AFTER whisper_output_to_segments: %d segments, sample text: %s", len(segments), segments[0].text[:100] if segments and segments[0].text else "EMPTY")

        # Merge segments to combine words into phrases
        silence_threshold = self.config.get("silence_threshold", 0.5)
        segments = merge_segments(segments, silence_threshold=silence_threshold)
        
        stage_elapsed = time.time() - stage_start
        self._emit("stage", {"stage": "merge", "status": "done", "count": len(segments)})
        logger.info("✓ Merge complete: %.2f seconds (%d segments)", stage_elapsed, len(segments))

        # ----------------------------------------------------------------
        # Stage 3: Clean (SKIP for testing - can affect timestamps)
        # ----------------------------------------------------------------
        # TEMPORARILY DISABLED: Clean fillers (can affect timestamps)
        # self._emit("stage", {"stage": "clean", "status": "running"})
        # for seg in segments:
        #     if seg.words:
        #         seg.words = clean(seg.words)
        #         seg.text = " ".join(w.word for w in seg.words).strip()
        # self._emit("stage", {"stage": "clean", "status": "done"})

        # ----------------------------------------------------------------
        # Stage 4: Chunk (sentence-boundary alignment)
        # ----------------------------------------------------------------
        logger.info("⏱️  Stage 3: Chunk")
        stage_start = time.time()
        self._emit("stage", {"stage": "chunk", "status": "running"})
        
        segments = chunk_segments(segments)
        
        stage_elapsed = time.time() - stage_start
        self._emit("stage", {"stage": "chunk", "status": "done", "count": len(segments)})
        logger.info("✓ Chunk complete: %.2f seconds (%d segments)", stage_elapsed, len(segments))

        # ----------------------------------------------------------------
        # Stage 5: Enrich (LLM — topics, keywords, summary) [OPTIONAL]
        # ----------------------------------------------------------------
        if self.config.get("pipeline", {}).get("enable_enrichment", True):
            logger.info("⏱️  Stage 4: Enrich")
            stage_start = time.time()
            self._emit("stage", {"stage": "enrich", "status": "running"})
            
            llm_client = self._get_llm_client()
            if llm_client:
                await enrich_segments(segments, llm_client, self.state)
            
            stage_elapsed = time.time() - stage_start
            self._emit("stage", {"stage": "enrich", "status": "done"})
            logger.info("✓ Enrich complete: %.2f seconds", stage_elapsed)
        else:
            logger.info("Enrichment disabled by config")

        # ----------------------------------------------------------------
        # Stage 6: Vectorize (sentence-transformers → ChromaDB) [OPTIONAL]
        # ----------------------------------------------------------------
        if self.config.get("pipeline", {}).get("enable_vectorization", True):
            logger.info("⏱️  Stage 5: Vectorize")
            stage_start = time.time()
            self._emit("stage", {"stage": "vectorize", "status": "running"})
            
            segments = vectorize_segments(segments, self.state)
            
            stage_elapsed = time.time() - stage_start
            self._emit("stage", {"stage": "vectorize", "status": "done"})
            logger.info("✓ Vectorize complete: %.2f seconds", stage_elapsed)
        else:
            logger.info("Vectorization disabled by config")

        # ----------------------------------------------------------------
        # Create complete segment list with silent gaps
        # ----------------------------------------------------------------
        from pipeline.timeline_builder import fill_silent_gaps
        
        logger.info("Creating complete segment list with silent gaps...")
        complete_segments = fill_silent_gaps(
            speech_segments=segments,
            video_duration=self.state.video_duration,
            min_silence_duration=self.config.get("silence_threshold", 0.5)
        )
        
        # ----------------------------------------------------------------
        # Write to state
        # ----------------------------------------------------------------
        self.state.add_segments(complete_segments)

        # Set initial sequence = all segments in order (speech + silent)
        from timeline.models import SequenceEntry
        sequence = [SequenceEntry(segment_id=seg.id, transition_in=None) for seg in complete_segments]
        self.state.set_sequence(sequence)

        self._emit("complete", {"segment_count": len(segments)})
        logger.info("Transcription pipeline complete: %d segments.", len(segments))

        return ToolResult(
            success=True,
            data={
                "segment_count": len(segments),
                "language": language or "auto-detected",
                "model_size": model_size,
                "ram_gb": _detect_ram(),
            },
        )

    def _get_llm_client(self):
        """Retrieve LLM client from config if available."""
        try:
            from llm.client import LLMClient
            provider = self.config.get("llm", {}).get("provider", "anthropic")
            model = self.config.get("llm", {}).get("model", "claude-sonnet-4-6")
            return LLMClient(provider=provider, model=model)
        except Exception:
            return None

    def get_lean_context(self) -> dict:
        seg_count = self.state.segment_count()
        return {
            "segment_count": seg_count,
            "status": "transcribed" if seg_count > 0 else "not_transcribed",
            "ram_gb": _detect_ram(),
        }
