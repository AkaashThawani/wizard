"""
media/ffmpeg_wrapper.py

FFmpeg command builder and executor.

All FFmpeg invocations go through this module.
Platform-specific encoder selection is the only platform conditional in the codebase.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_encoder() -> str:
    """
    Detect the best available H.264 encoder on this system.

    Returns one of:
      "h264_videotoolbox"  — Mac (hardware, fast)
      "h264_nvenc"         — Windows/Linux with NVIDIA GPU
      "libx264"            — software fallback (always available)
    """
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        return "libx264"

    system = platform.system()

    if system == "Darwin":
        # VideoToolbox is always available on Mac with FFmpeg
        if _encoder_available(ffmpeg, "h264_videotoolbox"):
            return "h264_videotoolbox"

    # Check for NVIDIA NVENC (Windows/Linux)
    if _encoder_available(ffmpeg, "h264_nvenc"):
        return "h264_nvenc"

    return "libx264"


def cut(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    """
    Extract a segment from a video file using stream copy (no re-encode).

    Fast — suitable for extracting individual segment files.
    Note: with stream copy, cuts are not frame-accurate; use encode() for precision.
    """
    ffmpeg = _require_ffmpeg()
    duration = end - start

    cmd = [
        ffmpeg,
        "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    _run(cmd, description=f"cut {start:.1f}–{end:.1f}s")


def export(
    inputs: list[dict],
    filter_complex: str,
    final_video: str,
    final_audio: str,
    output_path: str,
    encoder: str | None = None,
    resolution: str = "full",
) -> None:
    """
    Full export with filter_complex.

    Args:
        inputs: List of {"path": ..., "start": ..., "end": ...} dicts.
        filter_complex: FFmpeg filter_complex string.
        final_video: Label of the final video stream, e.g. "[mv5]".
        final_audio: Label of the final audio stream, e.g. "[ma5]".
        output_path: Where to write the output file.
        encoder: H.264 encoder to use. Auto-detected if None.
        resolution: "preview" (720p) or "full" (source resolution).
    """
    ffmpeg = _require_ffmpeg()
    if encoder is None:
        encoder = detect_encoder()

    cmd = [ffmpeg, "-y"]

    # Input files with trim (using -ss/-to for frame-accurate trim)
    for inp in inputs:
        cmd += [
            "-ss", f"{inp['start']:.3f}",
            "-to", f"{inp['end']:.3f}",
            "-i", inp["path"],
        ]

    if filter_complex:
        # Add scaling to filter_complex if needed (can't mix -vf with -filter_complex)
        if resolution == "preview" and final_video:
            filter_complex += f";{final_video}scale=-2:720[vout_scaled]"
            final_video = "[vout_scaled]"
        
        cmd += ["-filter_complex", filter_complex]
        if final_video:
            cmd += ["-map", final_video]
        if final_audio:
            cmd += ["-map", final_audio]
    else:
        # Simple case: single input, no filters
        cmd += ["-map", "0:v?", "-map", "0:a?"]
        
        # Resolution scaling for preview (only when not using filter_complex)
        if resolution == "preview":
            cmd += ["-vf", "scale=-2:720"]

    # Video codec
    cmd += ["-c:v", encoder]
    if encoder == "libx264":
        cmd += ["-preset", "fast", "-crf", "22"]
    elif encoder == "h264_nvenc":
        # NVIDIA GPU encoder - use fast preset for speed
        cmd += ["-preset", "fast", "-b:v", "3M"]  # Lower bitrate for faster encoding
    elif encoder == "h264_videotoolbox":
        cmd += ["-b:v", "5M"]

    # Audio
    cmd += ["-c:a", "aac", "-b:a", "192k"]

    cmd.append(output_path)
    _run(cmd, description=f"export → {Path(output_path).name}")


def extract_frame(
    source: str,
    timecode: float,
    output_path: str | None = None,
) -> str:
    """
    Extract a single frame as JPEG.

    Used by ColorAgent (future) to get keyframes for CLIP embedding.
    Returns the output path.
    """
    ffmpeg = _require_ffmpeg()

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)

    cmd = [
        ffmpeg,
        "-y",
        "-ss", f"{timecode:.3f}",
        "-i", source,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]
    _run(cmd, description=f"extract frame @{timecode:.1f}s")
    return output_path


def simple_concat(
    segment_files: list[str],
    output_path: str,
    encoder: str | None = None,
) -> None:
    """
    Concatenate a list of pre-extracted segment files.

    Uses a concat demuxer list file — efficient for many segments.
    """
    ffmpeg = _require_ffmpeg()
    if encoder is None:
        encoder = detect_encoder()

    # Write concat list to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        for seg_path in segment_files:
            # FFmpeg concat list format — paths must use forward slashes
            safe_path = seg_path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
        list_path = f.name

    try:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c:v", encoder,
            "-c:a", "aac",
            output_path,
        ]
        _run(cmd, description=f"concat {len(segment_files)} segments")
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _require_ffmpeg() -> str:
    path = _ffmpeg_path()
    if path is None:
        raise RuntimeError(
            "ffmpeg not found. Install FFmpeg and ensure it is on your PATH."
        )
    return path


def _encoder_available(ffmpeg: str, encoder: str) -> bool:
    """Check if an encoder is available in this FFmpeg build."""
    try:
        result = subprocess.run(
            [ffmpeg, "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return encoder in result.stdout
    except Exception:
        return False


def _run(cmd: list[str], description: str = "") -> None:
    """Run an FFmpeg command, raise RuntimeError on non-zero exit."""
    import time
    
    # Only log for major operations (export, concat), not frame extraction
    is_major = any(x in description for x in ["export", "concat", "cut"])
    
    if is_major:
        full_cmd = " ".join(cmd)
        logger.info("🎬 FFmpeg: %s", description)
        logger.debug("Command: %s", full_cmd)
    
    # Start timing
    start_time = time.time()
    
    # Set environment to suppress fontconfig warnings on Windows
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = "NUL"  # Suppress fontconfig warnings
    env["FONTCONFIG_PATH"] = "NUL"
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10-minute hard limit
        env=env,
    )
    
    # End timing
    end_time = time.time()
    elapsed = end_time - start_time
    
    if result.returncode != 0:
        logger.error("✗ FFmpeg failed: %s (%.2fs)", description, elapsed)
        
        # Extract actual error lines (skip banner/build info)
        # Banner lines start with spaces or contain "built with", "configuration"
        error_lines = [
            line for line in result.stderr.splitlines()
            if not line.startswith(" ") 
            and line.strip()
            and "built with" not in line.lower()
            and "configuration" not in line.lower()
            and "fontconfig error" not in line.lower()
        ]
        
        # Get last 20 error lines (actual errors)
        actual_error = "\n".join(error_lines[-20:]) if error_lines else result.stderr[-1000:]
        
        logger.error("Actual error:\n%s", actual_error)
        raise RuntimeError(f"FFmpeg failed [{description}]:\n{actual_error}")
    
    # Only log completion for major operations
    if is_major:
        logger.info("✓ FFmpeg done: %s (%.2fs)", description, elapsed)
