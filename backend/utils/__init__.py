"""
utils package

Device detection and model loading utilities for CUDA/Apple Silicon/CPU support.
"""

from .device import detect_device, DeviceConfig, DeviceType, ONNXProvider
from .model_loader import ModelCache

__all__ = [
    "detect_device",
    "DeviceConfig",
    "DeviceType",
    "ONNXProvider",
    "ModelCache",
]
