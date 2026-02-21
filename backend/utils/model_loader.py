"""
utils/model_loader.py

Centralized model loading utilities for ONNX models.

Provides thread-safe caching to prevent reloading models across requests.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class ModelCache:
    """
    Global model cache for ONNX models.
    
    Prevents reloading models across multiple requests.
    Thread-safe singleton pattern.
    
    Example:
        >>> cache = ModelCache.get_instance()
        >>> model = cache.get("whisper_small")
        >>> if model is None:
        ...     model = load_whisper_model()
        ...     cache.set("whisper_small", model)
    """
    
    _instance: ModelCache | None = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> ModelCache:
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def get(self, key: str) -> Any | None:
        """
        Get model from cache.
        
        Args:
            key: Model cache key
        
        Returns:
            Model instance or None if not cached
        """
        with self._cache_lock:
            return self._cache.get(key)
    
    def set(self, key: str, model: Any) -> None:
        """
        Store model in cache.
        
        Args:
            key: Model cache key
            model: Model instance to cache
        """
        with self._cache_lock:
            self._cache[key] = model
            logger.debug("Cached model: %s", key)
    
    def clear(self) -> None:
        """Clear all cached models."""
        with self._cache_lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Cleared %d cached models", count)
    
    def list_loaded(self) -> list[str]:
        """
        Get list of currently loaded model keys.
        
        Returns:
            List of model cache keys
        """
        with self._cache_lock:
            return list(self._cache.keys())
    
    def has(self, key: str) -> bool:
        """
        Check if model is cached.
        
        Args:
            key: Model cache key
        
        Returns:
            True if model is cached, False otherwise
        """
        with self._cache_lock:
            return key in self._cache
    
    def remove(self, key: str) -> bool:
        """
        Remove model from cache.
        
        Args:
            key: Model cache key
        
        Returns:
            True if model was removed, False if not found
        """
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug("Removed cached model: %s", key)
                return True
            return False


def load_whisper_onnx(model_size: str, providers: list[str]) -> Any:
    """
    Load Whisper model via ONNX Runtime using Optimum.
    
    Uses ModelCache to avoid reloading on subsequent calls.
    
    Args:
        model_size: "tiny", "base", "small", "medium", "large-v3"
        providers: ONNX execution providers list
    
    Returns:
        ORTModelForSpeechSeq2Seq instance
    
    Example:
        >>> providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        >>> model = load_whisper_onnx("small", providers)
    """
    cache = ModelCache.get_instance()
    cache_key = f"whisper_{model_size}_onnx"
    
    # Check cache first
    model = cache.get(cache_key)
    if model is not None:
        logger.debug("Using cached Whisper model: %s", model_size)
        return model
    
    # Load model
    logger.info("Loading Whisper model '%s' via ONNX Runtime...", model_size)
    
    try:
        from optimum.onnxruntime import ORTModelForSpeechSeq2Seq
        from transformers import AutoProcessor
        
        model_id = f"openai/whisper-{model_size}"
        
        # Load ONNX model (exports if not already exported)
        model = ORTModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            export=True,  # Auto-convert to ONNX if needed
            provider=providers[0] if providers else "CPUExecutionProvider",
        )
        
        # Load processor
        processor = AutoProcessor.from_pretrained(model_id)
        
        # Cache both model and processor
        cache.set(cache_key, model)
        cache.set(f"{cache_key}_processor", processor)
        
        logger.info("✓ Whisper model '%s' loaded via ONNX Runtime", model_size)
        return model
        
    except Exception as e:
        logger.error("Failed to load Whisper ONNX model: %s", e)
        raise


def load_clip_onnx(model_name: str, providers: list[str]) -> tuple:
    """
    Load CLIP model for visual analysis.
    
    Uses ModelCache to avoid reloading on subsequent calls.
    
    Args:
        model_name: HuggingFace model identifier (e.g., "openai/clip-vit-base-patch32")
        providers: ONNX execution providers
    
    Returns:
        (model, processor) tuple
    
    Example:
        >>> providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        >>> model, processor = load_clip_onnx("openai/clip-vit-base-patch32", providers)
    """
    cache = ModelCache.get_instance()
    cache_key = f"clip_{model_name.replace('/', '_')}_onnx"
    
    # Check cache first
    model = cache.get(cache_key)
    processor = cache.get(f"{cache_key}_processor")
    if model is not None and processor is not None:
        logger.debug("Using cached CLIP model: %s", model_name)
        return model, processor
    
    # Load model
    logger.info("Loading CLIP model '%s' via ONNX Runtime...", model_name)
    
    try:
        from optimum.onnxruntime import ORTModelForImageClassification
        from transformers import AutoProcessor
        
        # Load ONNX model
        model = ORTModelForImageClassification.from_pretrained(
            model_name,
            export=True,
            provider=providers[0] if providers else "CPUExecutionProvider",
        )
        
        # Load processor
        processor = AutoProcessor.from_pretrained(model_name)
        
        # Cache both
        cache.set(cache_key, model)
        cache.set(f"{cache_key}_processor", processor)
        
        logger.info("✓ CLIP model '%s' loaded via ONNX Runtime", model_name)
        return model, processor
        
    except Exception as e:
        logger.error("Failed to load CLIP ONNX model: %s", e)
        raise


def load_sentence_transformer_onnx(model_name: str, device: str) -> Any:
    """
    Load sentence-transformers model with ONNX backend.
    
    Uses ModelCache to avoid reloading on subsequent calls.
    
    Args:
        model_name: Model identifier (e.g., "all-MiniLM-L6-v2")
        device: "cuda", "mps", or "cpu"
    
    Returns:
        SentenceTransformer instance with backend="onnx"
    
    Example:
        >>> model = load_sentence_transformer_onnx("all-MiniLM-L6-v2", "cuda")
    """
    cache = ModelCache.get_instance()
    cache_key = f"sentence_transformer_{model_name.replace('/', '_')}_onnx_{device}"
    
    # Check cache first
    model = cache.get(cache_key)
    if model is not None:
        logger.debug("Using cached sentence-transformer model: %s", model_name)
        return model
    
    # Load model
    logger.info("Loading sentence-transformers model '%s' with ONNX backend on %s...", model_name, device)
    
    try:
        from sentence_transformers import SentenceTransformer
        
        # Load with ONNX backend
        model = SentenceTransformer(
            model_name,
            backend="onnx",
            device=device,
        )
        
        # Cache model
        cache.set(cache_key, model)
        
        logger.info("✓ Sentence-transformer model '%s' loaded with ONNX backend", model_name)
        return model
        
    except Exception as e:
        logger.error("Failed to load sentence-transformer ONNX model: %s", e)
        raise


def get_whisper_processor(model_size: str) -> Any:
    """
    Get Whisper processor from cache.
    
    Must be called after load_whisper_onnx().
    
    Args:
        model_size: Whisper model size
    
    Returns:
        AutoProcessor instance or None if not cached
    """
    cache = ModelCache.get_instance()
    cache_key = f"whisper_{model_size}_onnx_processor"
    return cache.get(cache_key)


def get_clip_processor(model_name: str) -> Any:
    """
    Get CLIP processor from cache.
    
    Must be called after load_clip_onnx().
    
    Args:
        model_name: CLIP model name
    
    Returns:
        AutoProcessor instance or None if not cached
    """
    cache = ModelCache.get_instance()
    cache_key = f"clip_{model_name.replace('/', '_')}_onnx_processor"
    return cache.get(cache_key)
