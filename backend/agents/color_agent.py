"""
agents/color_agent.py

ColorAgent — visual analysis using CLIP embeddings.

Extracts keyframes from video segments and generates CLIP embeddings
for visual similarity search and color analysis.

Tool: color.analyze {segment_ids: list[str]}
"""

from __future__ import annotations

import logging
import os
import tempfile
from PIL import Image
import numpy as np

from agents.base import BaseAgent, Tool, ToolResult, AgentStatus

logger = logging.getLogger(__name__)

# Lazy model cache
_clip_model = None
_clip_processor = None
_clip_device = None


def _get_clip_model(device_config=None):
    """Load CLIP model with GPU acceleration if available."""
    global _clip_model, _clip_processor, _clip_device
    
    if _clip_model is None:
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel
            from utils.device import detect_device
            
            if device_config is None:
                device_config = detect_device()
            
            # Determine device
            if device_config.device_type.value == "cuda" and torch.cuda.is_available():
                device = "cuda:0"
                torch_dtype = torch.float16
                logger.info("Loading CLIP model on GPU (CUDA)...")
            elif device_config.device_type.value == "mps" and torch.backends.mps.is_available():
                device = "mps"
                torch_dtype = torch.float16
                logger.info("Loading CLIP model on Apple Silicon (MPS)...")
            else:
                device = "cpu"
                torch_dtype = torch.float32
                logger.info("Loading CLIP model on CPU...")
            
            # Get model name from config
            model_name = "openai/clip-vit-base-patch32"
            
            # Load CLIP model and processor
            _clip_model = CLIPModel.from_pretrained(model_name).to(device).to(torch_dtype)
            _clip_processor = CLIPProcessor.from_pretrained(model_name)
            _clip_device = device
            
            logger.info("✓ CLIP model loaded successfully on %s", device)
            
        except Exception as e:
            logger.exception("Failed to load CLIP model: %s", e)
            raise
    
    return _clip_model, _clip_processor, _clip_device


class ColorAgent(BaseAgent):
    """
    Visual analysis agent using CLIP embeddings.
    
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
                name="color.analyze",
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
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("color.analyze", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name != "color.analyze":
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
        segment = self.state.get_segment(segment_id)
        if not segment:
            logger.warning("Segment %s not found", segment_id)
            return None
        
        source_path = self.state.source_path
        if not source_path or not os.path.exists(source_path):
            logger.warning("Source video not found: %s", source_path)
            return None
        
        # Extract keyframe at segment midpoint
        keyframe_time = segment.start + (segment.end - segment.start) / 2
        keyframe_path = await self._extract_keyframe(source_path, keyframe_time, segment_id)
        
        if not keyframe_path:
            return None
        
        try:
            # Analyze image with CLIP
            analysis = self._analyze_image(keyframe_path)
            
            # Store in state layers
            self.state.set_layer("color_agent", segment_id, analysis)
            
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
    
    async def _extract_keyframe(self, video_path: str, timestamp: float, segment_id: str) -> str | None:
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
                logger.warning("Failed to extract keyframe at %.2fs", timestamp)
                return None
                
        except Exception as e:
            logger.error("Keyframe extraction error: %s", e)
            return None
    
    def _analyze_image(self, image_path: str) -> dict:
        """Analyze image with CLIP and extract visual features."""
        import torch
        
        # Load CLIP model
        model, processor, device = _get_clip_model(self.device_config if hasattr(self, 'device_config') else None)
        
        # Load and process image
        image = Image.open(image_path).convert("RGB")
        
        # Get CLIP embedding
        inputs = processor(images=image, return_tensors="pt").to(device)
        
        with torch.no_grad():
            if device == "cuda:0":
                inputs = {k: v.half() for k, v in inputs.items()}
            image_features = model.get_image_features(**inputs)
            embedding = image_features.cpu().numpy()[0].tolist()
        
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
            
            collection.add(
                embeddings=[analysis["clip_embedding"]],
                documents=[segment.text or ""],
                metadatas=[metadata],
                ids=[segment_id]
            )
            
            logger.debug("Stored visual embedding for segment %s", segment_id)
            
        except Exception as e:
            logger.error("Failed to store in ChromaDB: %s", e)

    def get_lean_context(self) -> dict:
        layer = self.state.get_agent_layer("color_agent")
        return {
            "segments_analysed": len(layer),
            "visual_search_enabled": len(layer) > 0,
        }
