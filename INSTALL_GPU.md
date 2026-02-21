# GPU Acceleration Setup - NVIDIA CUDA

## Prerequisites

You have an NVIDIA GPU. Follow these steps to enable GPU acceleration.

## Step 1: Check CUDA Version

First, check if CUDA is installed:

```bash
nvidia-smi
```

This will show your GPU and CUDA version. Note the CUDA version (e.g., 11.8, 12.1, etc.).

If `nvidia-smi` doesn't work, install CUDA Toolkit from: https://developer.nvidia.com/cuda-downloads

## Step 2: Install PyTorch with CUDA Support

### For CUDA 11.8 (most common):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### For CUDA 12.1:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### For other CUDA versions:
Visit https://pytorch.org/get-started/locally/ and select your CUDA version.

## Step 3: Install ONNX Runtime GPU

```bash
# Uninstall CPU version first
pip uninstall onnxruntime

# Install GPU version
pip install onnxruntime-gpu
```

**Note:** `onnxruntime-gpu` requires CUDA 11.8 or 12.x. Make sure your PyTorch CUDA version matches!

## Step 4: Verify GPU Detection

Run the test script:

```bash
cd backend
python check_gpu.py
```

You should see:
```
✓ CUDA GPU detected - Ready for GPU acceleration!
  Using: NVIDIA GeForce RTX XXXX
```

## Step 5: Install Additional Dependencies (for Phase 3+)

Once GPU is working, install remaining dependencies:

```bash
# For ColorAgent (CLIP)
pip install open-clip-torch Pillow

# For AudioAgent
pip install librosa soundfile
```

## Troubleshooting

### "CUDA not available" after installing PyTorch

**Cause:** Wrong PyTorch version or CUDA toolkit mismatch.

**Fix:**
```bash
# Check what you installed
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"

# If CUDA shows False, reinstall with correct version
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### "CUDAExecutionProvider not available" in ONNX Runtime

**Cause:** CPU version of onnxruntime is installed.

**Fix:**
```bash
pip uninstall onnxruntime onnxruntime-gpu
pip install onnxruntime-gpu
```

### GPU Memory Errors

If you get out-of-memory errors:

1. Lower Whisper model size in `config.json`:
   ```json
   "whisper": {
     "model_size": "base"  // or "small" instead of "large-v3"
   }
   ```

2. Close other GPU applications (games, browsers, etc.)

## Expected Performance Improvement

With GPU enabled:
- **Whisper transcription**: 2-3x faster
- **CLIP (ColorAgent)**: 5-10x faster
- **Embeddings**: 2-3x faster

## Quick Install Commands (All-in-One)

```bash
# For CUDA 11.8 (most common)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip uninstall onnxruntime -y
pip install onnxruntime-gpu
pip install open-clip-torch Pillow librosa soundfile

# Verify
python check_gpu.py
```

## After GPU is Working

Your `check_gpu.py` output should show:

```
[1/5] Checking PyTorch installation...
✓ PyTorch version: 2.x.x+cu118
  CUDA available: True
  CUDA version: 11.8
  GPU device: NVIDIA GeForce RTX XXXX
  GPU memory: XX.X GB

[2/5] Checking ONNX Runtime installation...
✓ ONNX Runtime version: 1.x.x
  Available providers:
    - CUDAExecutionProvider  ← This is what you want to see!
    - CPUExecutionProvider

[3/5] Testing device detection module...
✓ CUDA detected: NVIDIA GeForce RTX XXXX (XX.X GB)
```

Once this is working, you're ready for Phase 3! 🚀
