"""
setup.py - Automatic GPU detection and dependency installation

Usage:
    python setup.py install

This will automatically detect GPU and install the appropriate packages:
- NVIDIA GPU → torch with CUDA, onnxruntime-gpu
- Apple Silicon → torch with MPS support
- CPU only → torch CPU, onnxruntime
"""

import os
import sys
import subprocess

# Bootstrap: Ensure setuptools is installed
try:
    from setuptools import setup, find_packages
    from setuptools.command.install import install
except ImportError:
    print("⚠️  setuptools not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    from setuptools import setup, find_packages
    from setuptools.command.install import install
    print("✓ setuptools installed successfully")


def detect_gpu():
    """Detect available GPU hardware."""
    print("\n" + "="*70)
    print("🔍 DETECTING HARDWARE...")
    print("="*70)
    
    # Check for NVIDIA GPU (CUDA)
    try:
        result = subprocess.run(
            ["nvidia-smi"], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Extract GPU name
            for line in result.stdout.split('\n'):
                if 'GeForce' in line or 'RTX' in line or 'GTX' in line or 'Tesla' in line:
                    gpu_name = line.strip()
                    print(f"✓ NVIDIA GPU detected: {gpu_name}")
                    print(f"✓ Will install: PyTorch with CUDA 12.1")
                    print(f"✓ Will install: onnxruntime-gpu")
                    return "cuda"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check for Apple Silicon
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "Apple" in result.stdout:
                print(f"✓ Apple Silicon detected: {result.stdout.strip()}")
                print(f"✓ Will install: PyTorch with MPS support")
                print(f"✓ Will install: onnxruntime (with CoreML)")
                return "mps"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    
    # CPU only
    print("ℹ️  No GPU detected (or GPU not available)")
    print("✓ Will install: PyTorch CPU version")
    print("✓ Will install: onnxruntime (CPU)")
    return "cpu"


def get_torch_packages(device_type):
    """Get PyTorch packages based on device type."""
    if device_type == "cuda":
        return [
            "torch>=2.0.0",
            "torchvision>=0.15.0",
            "--index-url", "https://download.pytorch.org/whl/cu121"
        ]
    elif device_type == "mps":
        return ["torch>=2.0.0", "torchvision>=0.15.0"]
    else:  # CPU
        return [
            "torch>=2.0.0",
            "torchvision>=0.15.0",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ]


def get_onnx_package(device_type):
    """Get ONNX Runtime package based on device type."""
    if device_type == "cuda":
        return "onnxruntime-gpu>=1.18.0"
    else:
        return "onnxruntime>=1.18.0"


class CustomInstall(install):
    """Custom installation to handle GPU-specific packages."""
    
    def run(self):
        print("\n" + "="*70)
        print("🚀 STARTING CUSTOM GPU-AWARE INSTALLATION")
        print("="*70)
        
        # Detect GPU FIRST
        device_type = detect_gpu()
        
        print("\n" + "="*70)
        print("📦 INSTALLING DEPENDENCIES...")
        print("="*70)
        
        # Install base dependencies first
        print("\n1️⃣  Upgrading pip, setuptools, wheel...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "--upgrade", "pip", "setuptools", "wheel"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            print("✓ Base tools upgraded")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Warning: Could not upgrade pip: {e}")
        
        # Install PyTorch with appropriate backend
        print(f"\n2️⃣  Installing PyTorch for {device_type.upper()}...")
        print("    (This may take a few minutes...)")
        torch_cmd = [sys.executable, "-m", "pip", "install"] + get_torch_packages(device_type)
        try:
            subprocess.check_call(torch_cmd)
            print(f"✓ PyTorch installed for {device_type.upper()}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install PyTorch: {e}")
            raise
        
        # Install ONNX Runtime
        print(f"\n3️⃣  Installing ONNX Runtime for {device_type.upper()}...")
        onnx_package = get_onnx_package(device_type)
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", onnx_package
            ])
            print(f"✓ ONNX Runtime installed: {onnx_package}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install ONNX Runtime: {e}")
            raise
        
        # Install other dependencies
        print("\n4️⃣  Installing other dependencies...")
        requirements_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements_base.txt")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "-r", requirements_file
            ])
            print("✓ All other dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install requirements: {e}")
            raise
        
        # Fix onnxruntime conflict (chromadb installs CPU version)
        if device_type == "cuda":
            print("\n4️⃣b Fixing onnxruntime conflict...")
            print("    (Replacing CPU version with GPU version)")
            try:
                # Uninstall CPU version if it exists
                subprocess.check_call([
                    sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                
                # Reinstall GPU version to ensure it's correct
                onnx_package = get_onnx_package(device_type)
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "--force-reinstall", onnx_package
                ])
                print("✓ ONNX Runtime conflict resolved (GPU version only)")
            except subprocess.CalledProcessError:
                print("⚠️  Warning: Could not fix onnxruntime conflict")
        
        # Run standard install (copy package files)
        print("\n5️⃣  Installing wizard-backend package...")
        install.run(self)
        print("✓ Package files installed")
        
        # Verify installation AFTER everything
        print("\n" + "="*70)
        print("✅ VERIFYING INSTALLATION...")
        print("="*70)
        
        try:
            import torch
            print(f"\n✓ PyTorch: {torch.__version__}")
            print(f"✓ CUDA available: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                print(f"✓ CUDA device: {torch.cuda.get_device_name(0)}")
                print(f"✓ CUDA version: {torch.version.cuda}")
            
            import onnxruntime as ort
            providers = ort.get_available_providers()
            print(f"\n✓ ONNX Runtime: {ort.__version__}")
            print(f"✓ ONNX Runtime providers:")
            for i, p in enumerate(providers, 1):
                print(f"    {i}. {p}")
            
            # Check for GPU providers
            has_gpu = any(p in ['CUDAExecutionProvider', 'TensorrtExecutionProvider'] for p in providers)
            if has_gpu:
                print("\n🎉 GPU ACCELERATION ENABLED!")
            else:
                print("\n⚠️  Warning: No GPU providers found in ONNX Runtime")
                print("    Whisper will use PyTorch CUDA, but missing ONNX GPU acceleration")
            
            print("\n" + "="*70)
            print("🎉 INSTALLATION COMPLETE!")
            print("="*70)
            print("\nNext steps:")
            print("  1. Verify: python check_gpu.py")
            print("  2. Start server: python app.py")
            print("  3. Upload a video and test GPU acceleration!")
            print("="*70)
            
        except Exception as e:
            print(f"\n⚠️  Warning: Could not verify installation: {e}")
            print("Run this to verify: python check_gpu.py")


# Read base requirements (without torch/onnxruntime)
with open("requirements_base.txt", "r") as f:
    base_requirements = [
        line.strip() 
        for line in f 
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="wizard-backend",
    version="1.0.0",
    description="Video editing AI backend with GPU acceleration",
    author="Wizard Team",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=base_requirements,
    cmdclass={
        "install": CustomInstall,
    },
    entry_points={
        "console_scripts": [
            "wizard=app:main",
        ],
    },
)
