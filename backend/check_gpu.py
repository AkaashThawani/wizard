"""
check_gpu.py

GPU and device detection verification script.
Run this to verify CUDA/Apple Silicon/CPU detection is working correctly.

Usage:
    python check_gpu.py
"""

import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

print("=" * 70)
print("DEVICE DETECTION TEST")
print("=" * 70)

# Test 1: Check if PyTorch is installed
print("\n[1/5] Checking PyTorch installation...")
torch_available = False
try:
    import torch
    torch_available = True
    print(f"✓ PyTorch version: {torch.__version__}")
    print(f"  CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  CUDA version: {torch.version.cuda}")
        print(f"  GPU device: {torch.cuda.get_device_name(0)}")
        print(f"  GPU memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB")
    
    # Check MPS (Apple Silicon)
    if hasattr(torch.backends, 'mps'):
        print(f"  MPS (Apple Silicon) available: {torch.backends.mps.is_available()}")
except ImportError:
    print("✗ PyTorch not installed (optional for this test)")
    print("  Install: pip install torch torchvision")

# Test 2: Check if ONNX Runtime is installed
print("\n[2/5] Checking ONNX Runtime installation...")
onnx_available = False
try:
    import onnxruntime as ort
    onnx_available = True
    print(f"✓ ONNX Runtime version: {ort.__version__}")
    print("  Available providers:")
    for provider in ort.get_available_providers():
        print(f"    - {provider}")
except ImportError:
    print("✗ ONNX Runtime not installed (continuing with tests)")
    print("  Install: pip install onnxruntime")

# Test 3: Test device detection module
print("\n[3/5] Testing device detection module...")
device_config = None
try:
    from utils.device import detect_device, log_device_info
    device_config = detect_device()
    print(f"✓ Device detection successful!")
    print(f"  Device type: {device_config.device_type.value}")
    print(f"  CUDA available: {device_config.cuda_available}")
    print(f"  MPS available: {device_config.mps_available}")
    if device_config.gpu_name:
        print(f"  GPU: {device_config.gpu_name}")
    if device_config.gpu_memory_gb:
        print(f"  GPU memory: {device_config.gpu_memory_gb:.1f} GB")
    print(f"  ONNX providers (priority order):")
    for i, provider in enumerate(device_config.onnx_providers, 1):
        print(f"    {i}. {provider}")
except Exception as e:
    print(f"✗ Device detection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test model cache
print("\n[4/5] Testing model cache...")
try:
    from utils.model_loader import ModelCache
    cache = ModelCache.get_instance()
    
    # Test cache operations
    cache.set("test_model", {"dummy": "model"})
    retrieved = cache.get("test_model")
    assert retrieved == {"dummy": "model"}, "Cache get/set failed"
    
    loaded = cache.list_loaded()
    assert "test_model" in loaded, "Model not in loaded list"
    
    cache.remove("test_model")
    assert cache.get("test_model") is None, "Cache remove failed"
    
    print("✓ Model cache working correctly")
    print(f"  Currently loaded models: {len(cache.list_loaded())}")
except Exception as e:
    print(f"✗ Model cache test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test config loading
print("\n[5/5] Testing config loading...")
try:
    import json
    from pathlib import Path
    
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print("✓ Config loaded successfully")
    print("  Device settings:")
    print(f"    cuda_enabled: {config['device']['cuda_enabled']}")
    print(f"    auto_detect: {config['device']['auto_detect']}")
    
    print("  Agent status:")
    for agent, settings in config['agents'].items():
        status = "✓ enabled" if settings['enabled'] else "✗ disabled"
        print(f"    {agent}: {status}")
    
    print("  Whisper settings:")
    print(f"    use_onnx: {config['whisper']['use_onnx']}")
    print(f"    device: {config['whisper']['device']}")
    
    print("  Embeddings settings:")
    print(f"    backend: {config['embeddings']['backend']}")
    print(f"    device: {config['embeddings']['device']}")
    
except Exception as e:
    print(f"✗ Config loading failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

if device_config and device_config.cuda_available:
    print("✓ CUDA GPU detected - Ready for GPU acceleration!")
    print(f"  Using: {device_config.gpu_name}")
elif device_config and device_config.mps_available:
    print("✓ Apple Silicon detected - Ready for GPU acceleration!")
    print(f"  Using: {device_config.gpu_name}")
else:
    print("⚠ No GPU detected - Will use CPU")
    print("  For GPU acceleration:")
    print("    - Windows/Linux: Install CUDA and onnxruntime-gpu")
    print("    - Mac: Apple Silicon (M1/M2/M3) automatically uses MPS")

if not torch_available:
    print("\n⚠ Note: PyTorch not installed")
    print("  Install for full functionality: pip install torch torchvision")

print(f"\n✓ All core tests passed!")
print("=" * 70)
