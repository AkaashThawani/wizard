"""
media/effect_compiler.py

Compiles the current timeline (sequence + edit_agent layers) into a single
FFmpeg filter_complex string and input list.

Design:
- Each effect type maps to a specific FFmpeg filter.
- All effects for a segment are chained together.
- Transitions are compiled between consecutive segments.
- The compiler returns (filter_complex, output_label) ready for ffmpeg_wrapper.export().

Supported effects (v1):
  volume, fade_in, fade_out, mute, caption, speed, crop

Supported transitions:
  cut (concat), crossfade (xfade), dissolve (xfade with dissolve)
"""

from __future__ import annotations

import logging
from timeline.models import SequenceEntry
from timeline.schema import EffectType, TransitionType

logger = logging.getLogger(__name__)


def _seg_get(seg, key, default=None):
    """Safely get from segment whether it's a dict or object."""
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def compile(
    sequence: list[SequenceEntry],
    layers: dict,
    segment_pool: dict,
) -> dict:
    """
    Compile the timeline into FFmpeg arguments.

    Returns:
        {
          "inputs": [{"path": ..., "start": ..., "end": ...}, ...],
          "filter_complex": "...",
          "final_video": "[vout]",
          "final_audio": "[aout]",
          "has_video": bool,
          "has_audio": bool,
        }
    """
    if not sequence:
        return {
            "inputs": [], "filter_complex": "", 
            "final_video": "", "final_audio": "",
            "has_video": False, "has_audio": False,
        }

    edit_layers = layers.get("edit_agent", {})

    inputs: list[dict] = []
    valid_entries = []  # (entry, idx, actual_start, actual_end, effects)

    # --- Pass 1: resolve all segments and build input list ---
    for entry in sequence:
        seg_id = entry.segment_id
        seg = segment_pool.get(seg_id)
        if seg is None:
            logger.warning("Segment %s not found in pool — skipping.", seg_id)
            continue

        edit = edit_layers.get(seg_id, {})
        trim = edit.get("trim", {})
        effects = edit.get("effects", [])

        seg_start = _seg_get(seg, "start", 0.0)
        seg_end = _seg_get(seg, "end", 0.0)
        seg_source = _seg_get(seg, "source", "")

        trim_start = trim.get("start") or 0.0
        trim_end = trim.get("end")

        actual_start = seg_start + trim_start
        actual_end = seg_end - trim_end if trim_end is not None else seg_end

        # Sanity check
        if actual_end <= actual_start:
            logger.warning("Segment %s has zero/negative duration after trim — skipping.", seg_id)
            continue

        idx = len(inputs)
        inputs.append({
            "path": seg_source,
            "start": actual_start,
            "end": actual_end,
            "seg_id": seg_id,
        })
        valid_entries.append((entry, idx, actual_start, actual_end, effects))

    if not inputs:
        return {
            "inputs": [], "filter_complex": "",
            "final_video": "", "final_audio": "",
            "has_video": False, "has_audio": False,
        }

    # --- Single segment: no filter_complex needed ---
    if len(inputs) == 1:
        return {
            "inputs": inputs,
            "filter_complex": "",
            "final_video": "",
            "final_audio": "",
            "has_video": True,
            "has_audio": True,
        }

    # --- Pass 2: build per-segment effect filters ---
    filter_lines: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    durations: list[float] = []

    for entry, idx, actual_start, actual_end, effects in valid_entries:
        v_in = f"[{idx}:v]"
        a_in = f"[{idx}:a]"
        v_out = f"[sv{idx}]"
        a_out = f"[sa{idx}]"
        duration = actual_end - actual_start

        v_chain, a_chain = _build_segment_filters(
            v_in, a_in, v_out, a_out, effects, duration
        )
        filter_lines.append(v_chain)
        filter_lines.append(a_chain)
        video_labels.append(v_out)
        audio_labels.append(a_out)
        durations.append(duration)

    # --- Pass 3: build transitions ---
    transition_lines, final_v, final_a = _build_transitions(
        valid_entries, video_labels, audio_labels, durations
    )
    filter_lines.extend(transition_lines)

    filter_complex = ";".join(f for f in filter_lines if f)

    return {
        "inputs": inputs,
        "filter_complex": filter_complex,
        "final_video": final_v,
        "final_audio": final_a,
        "has_video": True,
        "has_audio": True,
    }


def _build_segment_filters(
    v_in: str,
    a_in: str,
    v_out: str,
    a_out: str,
    effects: list[dict],
    duration: float,
) -> tuple[str, str]:
    """Build filter chains for a single segment. Returns (v_chain, a_chain)."""
    v_filters: list[str] = []
    a_filters: list[str] = []

    for eff in effects:
        if not eff.get("enabled", True):
            continue
        etype = eff.get("type", "")
        params = eff.get("params", {})
        if not isinstance(params, dict):
            logger.warning("Effect params is not a dict (got %s), using empty dict", type(params))
            params = {}

        if etype == EffectType.VOLUME:
            level = float(params.get("level", 1.0))
            a_filters.append(f"volume={level}")

        elif etype == EffectType.MUTE:
            a_filters.append("volume=0")

        elif etype == EffectType.FADE_IN:
            d = float(params.get("duration_s", 0.5))
            v_filters.append(f"fade=t=in:st=0:d={d}")
            a_filters.append(f"afade=t=in:st=0:d={d}")

        elif etype == EffectType.FADE_OUT:
            d = float(params.get("duration_s", 0.5))
            fade_start = max(0.0, duration - d)
            v_filters.append(f"fade=t=out:st={fade_start:.3f}:d={d}")
            a_filters.append(f"afade=t=out:st={fade_start:.3f}:d={d}")

        elif etype == EffectType.SPEED:
            factor = float(params.get("factor", 1.0))
            if factor != 1.0:
                v_filters.append(f"setpts={1.0/factor:.4f}*PTS")
                # atempo only supports 0.5-2.0, chain multiple for extreme values
                a_filters.extend(_build_atempo(factor))

        elif etype == EffectType.CROP:
            x = params.get("x", 0)
            y = params.get("y", 0)
            w = params.get("w", 1280)
            h = params.get("h", 720)
            v_filters.append(f"crop={w}:{h}:{x}:{y}")

        elif etype == EffectType.CAPTION:
            text = str(params.get("text", "")).strip()
            if not text:
                logger.warning("Caption effect has no text, skipping")
                continue
            # Escape special characters for FFmpeg
            text = text.replace("'", "\\'").replace(":", "\\:")
            v_filters.append(
                f"drawtext=text='{text}':fontsize=24:fontcolor=white"
                f":x=(w-text_w)/2:y=h-text_h-20:box=1:boxcolor=black@0.5"
            )

    v_chain = f"{v_in}{','.join(v_filters) if v_filters else 'null'}{v_out}"
    a_chain = f"{a_in}{','.join(a_filters) if a_filters else 'anull'}{a_out}"

    return v_chain, a_chain


def _build_atempo(factor: float) -> list[str]:
    """
    Build atempo filter chain. atempo only supports 0.5–2.0,
    so chain multiple filters for values outside that range.
    """
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return filters


def _build_transitions(
    valid_entries: list,
    video_labels: list[str],
    audio_labels: list[str],
    durations: list[float],
) -> tuple[list[str], str, str]:
    """Build transition filters between segments."""
    filter_lines: list[str] = []

    if not video_labels:
        return [], "", ""

    if len(video_labels) == 1:
        return [], video_labels[0], audio_labels[0]

    timeline_duration = durations[0]
    current_v = video_labels[0]
    current_a = audio_labels[0]
    merge_idx = 0

    for i in range(1, len(valid_entries)):
        entry, idx, actual_start, actual_end, effects = valid_entries[i]
        v2 = video_labels[i]
        a2 = audio_labels[i]
        transition = entry.transition_in

        out_v = f"[mv{merge_idx}]"
        out_a = f"[ma{merge_idx}]"
        merge_idx += 1

        if (
            transition is not None
            and transition.type in (TransitionType.CROSSFADE, TransitionType.DISSOLVE)
        ):
            d = float(transition.duration_s)
            # Clamp transition duration to shortest of the two segments
            max_d = min(durations[i - 1], durations[i]) * 0.9
            d = min(d, max_d)

            xfade_mode = "dissolve" if transition.type == TransitionType.DISSOLVE else "fade"
            offset = max(0.0, timeline_duration - d)

            filter_lines.append(
                f"{current_v}{v2}xfade=transition={xfade_mode}:duration={d:.3f}:offset={offset:.3f}{out_v}"
            )
            filter_lines.append(
                f"{current_a}{a2}acrossfade=d={d:.3f}{out_a}"
            )
            timeline_duration = timeline_duration + durations[i] - d
        else:
            # Plain cut via concat
            filter_lines.append(
                f"{current_v}{v2}concat=n=2:v=1:a=0{out_v}"
            )
            filter_lines.append(
                f"{current_a}{a2}concat=n=2:v=0:a=1{out_a}"
            )
            timeline_duration += durations[i]

        current_v = out_v
        current_a = out_a

    return filter_lines, current_v, current_a
