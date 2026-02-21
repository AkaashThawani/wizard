"""
media/video_info.py

ffprobe wrapper for extracting video metadata.
ffprobe is bundled with FFmpeg — no separate install required.
"""

from __future__ import annotations

import json
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)


def get_info(path: str) -> dict:
    """
    Return basic metadata for a video file.

    Returns:
        {
            "duration": float,   # seconds
            "fps": float,
            "width": int,
            "height": int,
            "has_audio": bool,
            "codec_video": str,
            "codec_audio": str,
        }

    Raises:
        RuntimeError if ffprobe is not available or the file cannot be probed.
    """
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError(
            "ffprobe not found. Install FFmpeg (includes ffprobe) and ensure "
            "it is on your PATH."
        )

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out on: {path}")

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed on '{path}': {result.stderr.strip()}"
        )

    data = json.loads(result.stdout)
    return _parse_ffprobe(data)


def _parse_ffprobe(data: dict) -> dict:
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = float(fmt.get("duration", 0.0))

    fps = 0.0
    width = 0
    height = 0
    codec_video = ""
    if video_stream:
        codec_video = video_stream.get("codec_name", "")
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        # FPS is stored as a fraction string e.g. "30000/1001"
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        if duration == 0.0:
            duration = float(video_stream.get("duration", 0.0))

    codec_audio = audio_stream.get("codec_name", "") if audio_stream else ""

    return {
        "duration": duration,
        "fps": round(fps, 3),
        "width": width,
        "height": height,
        "has_audio": audio_stream is not None,
        "codec_video": codec_video,
        "codec_audio": codec_audio,
    }
