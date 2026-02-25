"""
install.py - Automated installation with FFmpeg check and venv management

Usage:
    python install.py

This will:
1. Check if FFmpeg is installed
2. Create a virtual environment (.venv) if it doesn't exist
3. Install all dependencies with GPU detection
4. Verify the installation
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path


def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_ffmpeg():
    """Check if FFmpeg is installed and accessible."""
    print_header("🔍 CHECKING FFMPEG")
    
    ffmpeg_path = shutil.which("ffmpeg")
    
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Extract version from first line
                version_line = result.stdout.split('\n')[0]
                print(f"✓ FFmpeg found: {ffmpeg_path}")
                print(f"✓ Version: {version_line}")
                return True
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"⚠️  FFmpeg found but couldn't get version: {e}")
            return True  # Still proceed if ffmpeg exists
    
    # FFmpeg not found
    print("❌ FFmpeg is NOT installed or not in PATH!")
    print("\n" + "=" * 70)
    print("📦 FFMPEG INSTALLATION INSTRUCTIONS")
    print("=" * 70)
    
    system = platform.system()
    
    if system == "Windows":
        print("\n🪟 Windows:")
        print("  1. Download from: https://ffmpeg.org/download.html")
        print("  2. Or use package manager:")
        print("     • Chocolatey: choco install ffmpeg")
        print("     • Scoop: scoop install ffmpeg")
        print("  3. Add to PATH and restart terminal")
        
    elif system == "Darwin":  # macOS
        print("\n🍎 macOS:")
        print("  brew install ffmpeg")
        
    elif system == "Linux":
        print("\n🐧 Linux:")
        print("  • Ubuntu/Debian: sudo apt install ffmpeg")
        print("  • Fedora: sudo dnf install ffmpeg")
        print("  • Arch: sudo pacman -S ffmpeg")
    
    print("\n" + "=" * 70)
    print("⚠️  Please install FFmpeg and run this script again.")
    print("=" * 70)
    return False


def get_venv_path():
    """Get the path to the virtual environment directory."""
    backend_dir = Path(__file__).parent
    return backend_dir / ".venv"


def get_python_executable():
    """Get the path to the Python executable in the venv."""
    venv_path = get_venv_path()
    
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"


def get_pip_executable():
    """Get the path to pip in the venv."""
    venv_path = get_venv_path()
    
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"


def create_venv():
    """Create a virtual environment if it doesn't exist."""
    venv_path = get_venv_path()
    
    print_header("🐍 VIRTUAL ENVIRONMENT SETUP")
    
    if venv_path.exists():
        python_exe = get_python_executable()
        if python_exe.exists():
            print(f"✓ Virtual environment already exists: {venv_path}")
            print(f"✓ Python: {python_exe}")
            return True
        else:
            print(f"⚠️  Venv directory exists but Python not found. Recreating...")
            shutil.rmtree(venv_path)
    
    print(f"📦 Creating virtual environment at: {venv_path}")
    print("   (This may take a moment...)")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "venv", str(venv_path)
        ])
        print(f"✓ Virtual environment created successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return False


def upgrade_pip():
    """Upgrade pip in the virtual environment."""
    print_header("📦 UPGRADING PIP")
    
    pip_exe = get_pip_executable()
    
    try:
        subprocess.check_call([
            str(pip_exe), "install", "--upgrade", "pip", "setuptools", "wheel"
        ])
        print("✓ pip, setuptools, and wheel upgraded")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Could not upgrade pip: {e}")
        return True  # Continue anyway


def install_dependencies():
    """Install all dependencies using setup.py."""
    print_header("📦 INSTALLING DEPENDENCIES")
    
    python_exe = get_python_executable()
    backend_dir = Path(__file__).parent
    
    print("🚀 Running setup.py install...")
    print("   (This will detect your GPU and install appropriate packages)")
    print("   (This may take several minutes...)")
    print()
    
    try:
        # Run setup.py install in the venv
        subprocess.check_call([
            str(python_exe), "setup.py", "install"
        ], cwd=str(backend_dir))
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def print_activation_instructions():
    """Print instructions for activating the virtual environment."""
    venv_path = get_venv_path()
    system = platform.system()
    
    print_header("🎯 VIRTUAL ENVIRONMENT ACTIVATION")
    
    print("\n📝 To activate the virtual environment:")
    
    if system == "Windows":
        print(f"\n  • PowerShell:")
        print(f"    {venv_path}\\Scripts\\Activate.ps1")
        print(f"\n  • Command Prompt:")
        print(f"    {venv_path}\\Scripts\\activate.bat")
    else:
        print(f"\n  • Bash/Zsh:")
        print(f"    source {venv_path}/bin/activate")
    
    print("\n📝 To run the application:")
    print("  python app.py")
    
    print("\n📝 To deactivate:")
    print("  deactivate")


def main():
    """Main installation flow."""
    print("\n" + "=" * 70)
    print("  🧙 WIZARD BACKEND INSTALLER")
    print("=" * 70)
    
    # Step 1: Check FFmpeg
    if not check_ffmpeg():
        sys.exit(1)
    
    # Step 2: Create venv
    if not create_venv():
        sys.exit(1)
    
    # Step 3: Upgrade pip
    upgrade_pip()
    
    # Step 4: Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Success!
    print_header("🎉 INSTALLATION COMPLETE!")
    
    print("\n✅ All dependencies installed successfully")
    print("✅ Virtual environment ready")
    print("✅ GPU detection and configuration complete")
    
    print_activation_instructions()
    
    print("\n" + "=" * 70)
    print("  🚀 READY TO GO!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Activate the virtual environment (see above)")
    print("  2. Verify: python check_gpu.py")
    print("  3. Start server: python app.py")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Installation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
