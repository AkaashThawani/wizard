"""
utils/device.py

Device detection and configuration for CUDA/Apple Silicon/CPU support.

Automatically detects available hardware and configures ONNX Runtime providers
for optimal performance. Priority: CUDA > Apple Silicon (MPS) > CPU.
"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    """Available device types for model inference."""
    CUDA = "cuda"
    APPLE_SILICON = "mps"  # Metal Performance Shaders
    CPU = "cpu"


class ONNXProvider(str, Enum):
    """ONNX Runtime execution providers."""
    CUDA = "CUDAExecutionProvider"
    TENSORRT = "TensorrtExecutionProvider"
    COREML = "CoreMLExecutionProvider"
    DIRECTML = "DmlExecutionProvider"  # Windows DirectX
    CPU = "CPUExecutionProvider"


@dataclass
class DeviceConfig:
    """Device detection and configuration result."""
    device_type: DeviceType
    onnx_providers: list[str]
    cuda_available: bool
    mps_available: bool
    gpu_name: str | None
    gpu_memory_gb: float | None


class DeviceDetector:
    """
    Singleton device detection manager.
    
    Detects available hardware once and caches the result for reuse.
    """
    
    _instance: DeviceDetector | None = None
    _config: DeviceConfig | None = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> DeviceDetector:
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def detect(self) -> DeviceConfig:
        """
        Run device detection and return configuration.
        
        Detection priority:
        1. CUDA (NVIDIA GPU on Windows/Linux)
        2. Apple Silicon MPS (Mac M1/M2/M3)
        3. CPU (fallback)
        """
        if self._config is not None:
            return self._config
        
        cuda_available = False
        mps_available = False
        gpu_name = None
        gpu_memory_gb = None
        
        # Check PyTorch CUDA availability
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                # Get GPU memory in GB
                gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                logger.info("✓ CUDA detected: %s (%.1f GB)", gpu_name, gpu_memory_gb)
        except Exception as e:
            logger.debug("CUDA check failed: %s", e)
        
        # Check Apple Silicon MPS availability
        if not cuda_available:
            try:
                import torch
                mps_available = torch.backends.mps.is_available() and torch.backends.mps.is_built()
                if mps_available:
                    system = platform.system()
                    machine = platform.machine()
                    gpu_name = f"{system} {machine}"
                    logger.info("✓ Apple Silicon (MPS) detected: %s", gpu_name)
            except Exception as e:
                logger.debug("MPS check failed: %s", e)
        
        # Determine device type and ONNX providers
        if cuda_available:
            device_type = DeviceType.CUDA
            onnx_providers = get_onnx_providers(cuda_enabled=True)
        elif mps_available:
            device_type = DeviceType.APPLE_SILICON
            onnx_providers = get_onnx_providers(cuda_enabled=False)
        else:
            device_type = DeviceType.CPU
            onnx_providers = [ONNXProvider.CPU.value]
            logger.info("⚠ No GPU detected, using CPU")
        
        self._config = DeviceConfig(
            device_type=device_type,
            onnx_providers=onnx_providers,
            cuda_available=cuda_available,
            mps_available=mps_available,
            gpu_name=gpu_name,
            gpu_memory_gb=gpu_memory_gb,
        )
        
        log_device_info(self._config)
        return self._config
    
    def get_config(self) -> DeviceConfig:
        """Get cached device configuration (runs detection if not cached)."""
        if self._config is None:
            return self.detect()
        return self._config
    
    def refresh(self) -> DeviceConfig:
        """Re-run device detection (clears cache)."""
        self._config = None
        return self.detect()


def detect_device() -> DeviceConfig:
    """
    Detect available hardware and return optimal configuration.
    
    This is the main entry point for device detection.
    Uses singleton pattern to avoid repeated detection.
    
    Priority: CUDA > Apple Silicon (MPS) > CPU
    
    Returns:
        DeviceConfig with device_type and onnx_providers list
    
    Example:
        >>> config = detect_device()
        >>> print(config.device_type)  # DeviceType.CUDA
        >>> print(config.onnx_providers)  # ['CUDAExecutionProvider', 'CPUExecutionProvider']
    """
    detector = DeviceDetector.get_instance()
    return detector.detect()


def get_onnx_providers(cuda_enabled: bool = True) -> list[str]:
    """
    Get ordered list of ONNX Runtime providers based on availability.
    
    FORCED CPU-ONLY MODE: Always returns CPU provider to avoid CUDA 13.0/12.1 mismatch.
    
    Args:
        cuda_enabled: Whether to include CUDA providers in priority list (IGNORED - always CPU)
    
    Returns:
        Ordered list of ONNX provider strings (CPU only)
    
    Example:
        >>> providers = get_onnx_providers(cuda_enabled=True)
        >>> # ['CPUExecutionProvider']
    """
    # FORCE CPU ONLY - CUDA 13.0 driver incompatible with CUDA 12.1 binaries
    logger.info("⚠️  FORCED CPU-ONLY MODE: GPU execution disabled due to CUDA version mismatch")
    logger.info("   Your system: CUDA 13.0 (driver 581.15)")
    logger.info("   Required: CUDA 12.1 (for PyTorch/ONNX binaries)")
    logger.info("   Using CPU for all models (safe, reliable, fast enough)")
    
    return [ONNXProvider.CPU.value]


def get_torch_device() -> str:
    """
    Get PyTorch device string for models not using ONNX.
    
    Returns: "cuda", "mps", or "cpu"
    
    Example:
        >>> device = get_torch_device()
        >>> model.to(device)
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def log_device_info(config: DeviceConfig) -> None:
    """
    Log detected device information for debugging.
    
    Args:
        config: DeviceConfig instance to log
    """
    logger.info("=" * 60)
    logger.info("Device Configuration:")
    logger.info("  Device Type: %s", config.device_type.value.upper())
    logger.info("  CUDA Available: %s", config.cuda_available)
    logger.info("  Apple Silicon (MPS) Available: %s", config.mps_available)
    
    if config.gpu_name:
        logger.info("  GPU: %s", config.gpu_name)
    if config.gpu_memory_gb:
        logger.info("  GPU Memory: %.1f GB", config.gpu_memory_gb)
    
    logger.info("  ONNX Providers (priority order):")
    for i, provider in enumerate(config.onnx_providers, 1):
        logger.info("    %d. %s", i, provider)
    logger.info("=" * 60)
