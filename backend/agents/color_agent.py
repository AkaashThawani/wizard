"""
agents/color_agent.py

ColorAgent — visual analysis using CLIP embeddings via ONNX Runtime.

Extracts keyframes from video segments and generates CLIP embeddings
for visual similarity search and color analysis.

Tool: color.analyze {segment_ids: list[str]}
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from PIL import Image
import numpy as np

from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lazy model cache
_clip_model = None
_clip_processor = None
_clip_device = None
_clip_lock = threading.Lock()


def _get_clip_model(device_config=None):
    """Load CLIP model via raw ONNX Runtime (no Optimum wrapper)."""
    global _clip_model, _clip_processor, _clip_device
    
    # Thread-safe model loading: only first thread loads, others wait
    with _clip_lock:
        if _clip_model is None:
            try:
                import onnxruntime as ort
                from transformers import CLIPProcessor
                from utils.device import detect_device
                
                if device_config is None:
                    device_config = detect_device()
                
                model_name = "openai/clip-vit-base-patch32"
                providers = device_config.onnx_providers
                
                logger.info("Loading CLIP model via raw ONNX Runtime...")
                logger.info("  Model: %s", model_name)
                logger.info("  Providers: %s", providers)
                
                # Check for local ONNX model first
                import os
                local_path = os.path.join(os.path.dirname(__file__), "..", "models", "clip-vit-base-patch32-onnx", "onnx", "model.onnx")
                
                if os.path.exists(local_path):
                    logger.info("  Using local ONNX model from: %s", local_path)
                    onnx_path = local_path
                else:
                    logger.error("  Local ONNX model not found at: %s", local_path)
                    raise FileNotFoundError(f"CLIP ONNX model not found at {local_path}")
                
                # Load ONNX model with raw ONNX Runtime (no Optimum wrapper)
                _clip_model = ort.InferenceSession(
                    onnx_path,
                    providers=providers if providers else ["CPUExecutionProvider"]
                )
                
                # Load processor
                _clip_processor = CLIPProcessor.from_pretrained(model_name)
                _clip_device = providers[0] if providers else "CPUExecutionProvider"
                
                logger.info("✓ CLIP model loaded successfully via raw ONNX Runtime")
                logger.info("  Active provider: %s", _clip_device)
                logger.info("  Model inputs: %s", [inp.name for inp in _clip_model.get_inputs()])
                logger.info("  Model outputs: %s", [out.name for out in _clip_model.get_outputs()])
                
            except Exception as e:
                logger.exception("Failed to load CLIP model: %s", e)
                raise
    
    return _clip_model, _clip_processor, _clip_device


class ColorAgent(BaseAgent):
    """
    Visual analysis agent using CLIP embeddings via ONNX Runtime.
    
    Capabilities:
    - Extract keyframes from video segments
    - Generate CLIP embeddings for visual similarity search
    - Analyze brightness and dominant colors
    - Store embeddings in ChromaDB chroma/visual collection
    """

    def description(self) -> str:
        return "Analyses visual content of segments using CLIP embeddings for visual search."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="color_analyze",
                description=(
                    "Analyse the visual content of specified segments. "
                    "Extracts keyframes and generates CLIP embeddings stored in "
                    "chroma/visual for visual similarity search. "
                    "Also analyzes brightness and dominant colors."
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
                name="color_reanalyze_segment",
                description=(
                    "Re-analyze visual content of a specific segment. "
                    "Useful after edits (trim, effects) to get updated visual analysis. "
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
        result = await self.execute_tool("color_analyze", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def analyze_full_video(self) -> list[dict]:
        """
        Analyze entire video per-second in parallel.
        
        Returns:
            List of dicts, one per second:
            [
                {"time": 0.0, "brightness": 0.12, "color": "#1e201f", "saturation": 0.028, "clip_embedding": [...]},
                {"time": 1.0, "brightness": 0.13, "color": "#1f211f", "saturation": 0.029, "clip_embedding": [...]},
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
        logger.info("ColorAgent analyzing %d seconds in parallel...", num_seconds)
        
        # Analyze all seconds in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._analyze_single_second, source_path, t): t
                for t in range(num_seconds)
            }
            
            results = {}
            for future in concurrent.futures.as_completed(futures):
                t = futures[future]
                try:
                    results[t] = future.result()
                except Exception as exc:
                    logger.error("Failed to analyze second %d: %s", t, exc)
                    # Use placeholder data
                    results[t] = {
                        "time": float(t),
                        "brightness": 0.0,
                        "dominant_color": "#000000",
                        "saturation": 0.0,
                        "clip_embedding": [0.0] * 512,
                        "dimensions": [0, 0]
                    }
        
        # Build timeline array
        timeline = [results[t] for t in sorted(results.keys())]
        logger.info("✓ ColorAgent analyzed %d seconds", len(timeline))
        return timeline

    def _analyze_single_second(self, video_path: str, second: int) -> dict:
        """Analyze video at specific second."""
        # Extract keyframe at this second
        keyframe_path = self._extract_keyframe(video_path, float(second), f"sec_{second}")
        
        if not keyframe_path:
            return {
                "time": float(second),
                "brightness": 0.0,
                "dominant_color": "#000000",
                "saturation": 0.0,
                "clip_embedding": [0.0] * 512,
                "dimensions": [0, 0]
            }
        
        try:
            # Analyze image
            analysis = self._analyze_image(keyframe_path)
            analysis["time"] = float(second)
            return analysis
        finally:
            if os.path.exists(keyframe_path):
                try:
                    os.remove(keyframe_path)
                except Exception:
                    pass

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name == "color_reanalyze_segment":
            return await self._reanalyze_segment_tool(params)
        
        if name != "color_analyze":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        try:
            segment_ids = params.get("segment_ids") or list(self.state.get_all_segments().keys())
            
            if not segment_ids:
                return ToolResult(
                    success=True,
                    data={"segments_processed": 0, "message": "No segments to analyze"},
                )
            
            logger.info("ColorAgent analyzing %d segments...", len(segment_ids))
            
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
            
            logger.info("✓ ColorAgent processed %d/%d segments", processed, len(segment_ids))
            
            return ToolResult(
                success=True,
                data={
                    "segments_processed": processed,
                    "segments_total": len(segment_ids),
                    "errors": errors if errors else None,
                },
            )
            
        except Exception as exc:
            logger.exception("ColorAgent analysis failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _analyze_segment(self, segment_id: str) -> dict | None:
        """Analyze a single segment with CLIP."""
        segment = self.state.get_effective_segment(segment_id)
        if not segment:
            logger.warning("Segment %s not found", segment_id)
            return None
        
        source_path = self.state.source_path
        if not source_path or not os.path.exists(source_path):
            logger.warning("Source video not found: %s", source_path)
            return None
        
        # Extract keyframe at segment midpoint
        keyframe_time = segment.start + (segment.end - segment.start) / 2
        keyframe_path = self._extract_keyframe(source_path, keyframe_time, segment_id)
        
        if not keyframe_path:
            return None
        
        try:
            # Analyze image with CLIP
            analysis = self._analyze_image(keyframe_path)
            
            # Store in state layers
            self.state.set_layer("color_agent", segment_id, analysis)
            logger.info("✓ ColorAgent: Stored analysis for %s - brightness=%.2f, color=%s", 
                       segment_id, analysis["brightness"], analysis["dominant_color"])
            
            # Store embedding in ChromaDB
            self._store_in_chromadb(segment_id, analysis)
            
            return analysis
            
        finally:
            # Clean up temp keyframe
            if os.path.exists(keyframe_path):
                try:
                    os.remove(keyframe_path)
                except Exception:
                    pass
    
    def _extract_keyframe(self, video_path: str, timestamp: float, segment_id: str) -> str | None:
        """Extract keyframe from video at specified timestamp."""
        try:
            from media.ffmpeg_wrapper import extract_frame
            
            # Create temp file for keyframe
            temp_dir = tempfile.gettempdir()
            keyframe_path = os.path.join(temp_dir, f"keyframe_{segment_id}_{int(timestamp*1000)}.jpg")
            
            # Extract frame using FFmpeg
            success = extract_frame(video_path, timestamp, keyframe_path)
            
            if success and os.path.exists(keyframe_path):
                return keyframe_path
            else:
                logger.error("❌ FFmpeg frame extraction failed:")
                logger.error("  Video: %s", video_path)
                logger.error("  Video exists: %s", os.path.exists(video_path))
                logger.error("  Timestamp: %.2fs", timestamp)
                logger.error("  Target path: %s", keyframe_path)
                logger.error("  File was created: %s", os.path.exists(keyframe_path))
                return None
                
        except Exception as e:
            logger.error("❌ Keyframe extraction exception:")
            logger.error("  Error: %s", e)
            logger.error("  Video: %s", video_path)
            logger.error("  Timestamp: %.2fs", timestamp)
            import traceback
            logger.error("  Traceback: %s", traceback.format_exc())
            return None
    
    def _analyze_image(self, image_path: str) -> dict:
        """Analyze image with CLIP via ONNX Runtime and extract visual features."""
        import torch
        
        # Load CLIP model
        model, processor, device = _get_clip_model(self.device_config if hasattr(self, 'device_config') else None)
        
        # Load and process image
        image = Image.open(image_path).convert("RGB")
        
        # CLIP ONNX model requires BOTH image and text inputs
        # Process image to get pixel_values
        image_inputs = processor(images=image, return_tensors="pt")
        
        # Process dummy text (empty string) to get input_ids and attention_mask
        # This satisfies the ONNX model's requirement for text inputs
        text_inputs = processor(text=[""], return_tensors="pt", padding=True)
        
        # Merge both inputs (pixel_values + input_ids + attention_mask)
        inputs = {**image_inputs, **text_inputs}
        
        # Raw ONNX inference using session.run()
        try:
            # Convert PyTorch tensors to numpy for ONNX
            onnx_inputs = {}
            for key, value in inputs.items():
                if hasattr(value, 'numpy'):
                    onnx_inputs[key] = value.numpy()
                else:
                    onnx_inputs[key] = value
            
            # Run inference
            output_names = [out.name for out in model.get_outputs()]
            outputs = model.run(output_names, onnx_inputs)
            
            # Extract embedding from raw ONNX outputs
            # CLIP outputs: [logits_per_image, logits_per_text, text_embeds, image_embeds]
            # We want image_embeds which is at index 3
            if len(outputs) >= 4:
                embedding = outputs[3]  # image_embeds at index 3
                logger.debug("Using image_embeds (outputs[3]) from CLIP")
            else:
                raise RuntimeError(f"Expected 4 outputs from CLIP, got {len(outputs)}")
            
            # Convert to list (embedding is already numpy array)
            if len(embedding.shape) > 1:
                # If shape is (1, 512), squeeze to (512,)
                embedding = embedding.squeeze()
            embedding = embedding.tolist()
            
        except Exception as e:
            logger.error("❌ CLIP inference failed: %s", e)
            raise
        
        # Analyze color properties
        img_array = np.array(image)
        brightness = float(np.mean(img_array) / 255.0)
        
        # Get dominant color (simple mean RGB)
        mean_color = np.mean(img_array.reshape(-1, 3), axis=0).astype(int)
        dominant_color = "#{:02x}{:02x}{:02x}".format(*mean_color)
        
        # Calculate saturation
        rgb_normalized = img_array / 255.0
        max_rgb = rgb_normalized.max(axis=2)
        min_rgb = rgb_normalized.min(axis=2)
        saturation = float(np.mean(max_rgb - min_rgb))
        
        return {
            "clip_embedding": embedding,
            "brightness": brightness,
            "dominant_color": dominant_color,
            "saturation": saturation,
            "dimensions": list(image.size),
        }
    
    def _store_in_chromadb(self, segment_id: str, analysis: dict):
        """Store visual embedding in ChromaDB."""
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
            collection = client.get_or_create_collection(name="visual")
            
            # Add embedding
            segment = self.state.get_segment(segment_id)
            metadata = {
                "segment_id": segment_id,
                "start": segment.start,
                "end": segment.end,
                "brightness": analysis["brightness"],
                "dominant_color": analysis["dominant_color"],
                "saturation": analysis["saturation"],
            }
            
            # Ensure embedding is pure Python list to prevent ChromaDB debug output
            collection.add(
                embeddings=[safe_embedding(analysis["clip_embedding"])],
                documents=[segment.text or ""],
                metadatas=[metadata],
                ids=[segment_id]
            )
            
            logger.debug("Stored visual embedding for segment %s", segment_id)
            
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
            logger.info("ColorAgent re-analyzing segment %s (with current edits)...", segment_id)
            
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
                        "brightness": result["brightness"],
                        "dominant_color": result["dominant_color"],
                        "saturation": result["saturation"],
                        "dimensions": result["dimensions"],
                    },
                    "message": f"Re-analyzed segment {segment_id} with current edits applied"
                },
            )
            
        except Exception as exc:
            logger.exception("ColorAgent reanalysis failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    def get_lean_context(self) -> dict:
        layer = self.state.get_agent_layer("color_agent")
        return {
            "segments_analysed": len(layer),
            "visual_search_enabled": len(layer) > 0,
        }
