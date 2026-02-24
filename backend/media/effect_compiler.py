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


def compile(
    sequence: list[SequenceEntry],
    layers: dict,                 # state._data["layers"]
    segment_pool: dict,           # state._data["segment_pool"]
) -> dict:
    """
    Compile the timeline into FFmpeg arguments.

    Returns:
        {
          "inputs": [{"path": ..., "start": ..., "end": ...}, ...],
          "filter_complex": "...",
          "output_label": "[vout][aout]",
          "has_video": bool,
          "has_audio": bool,
        }

    Each input corresponds to one segment (with trim applied).
    filter_complex chains all per-segment effects + transitions.
    """
    if not sequence:
        return {"inputs": [], "filter_complex": "", "output_label": "", "has_video": False, "has_audio": False}

    edit_layers = layers.get("edit_agent", {})

    inputs: list[dict] = []
    video_chains: list[str] = []
    audio_chains: list[str] = []

    for idx, entry in enumerate(sequence):
        seg_id = entry.segment_id
        seg = segment_pool.get(seg_id)
        if seg is None:
            logger.warning("Segment %s not found in pool — skipping.", seg_id)
            continue

        edit = edit_layers.get(seg_id, {})
        trim = edit.get("trim", {})
        effects = edit.get("effects", [])

        # Determine actual in/out points
        seg_start = seg["start"]
        seg_end = seg["end"]

        trim_start = trim.get("start")
        trim_end = trim.get("end")

        actual_start = seg_start + (trim_start or 0.0)
        actual_end = seg_end - (trim_end or 0.0) if trim_end is not None else seg_end

        inputs.append({
            "path": seg["source"],
            "start": actual_start,
            "end": actual_end,
            "seg_id": seg_id,
        })

        i = len(inputs) - 1
        v_in = f"[{i}:v]"
        a_in = f"[{i}:a]"

        # Build per-segment filter chain
        v_chain, a_chain = _build_segment_filters(
            v_in, a_in, effects, idx, actual_start, actual_end
        )

        video_chains.append(v_chain)
        audio_chains.append(a_chain)

    # Build complete filter_complex
    filter_lines = []
    
    # 1. Add all segment filters first (apply effects to each input)
    for v_chain, a_chain in zip(video_chains, audio_chains):
        filter_lines.append(v_chain)
        filter_lines.append(a_chain)
    
    # 2. Extract labels from chains for transition building
    video_labels = [f"[sv{i}]" for i in range(len(video_chains))]
    audio_labels = [f"[sa{i}]" for i in range(len(audio_chains))]
    
    # 3. Build transitions between segments
    transition_lines, final_v, final_a = _build_transitions(
        sequence, segment_pool, edit_layers, video_labels, audio_labels
    )
    
    # 4. Add transition filters
    filter_lines.extend(transition_lines)

    filter_complex = ";".join(filter_lines) if filter_lines else ""
    output_label = f"{final_v}{final_a}" if final_v and final_a else ""

    return {
        "inputs": inputs,
        "filter_complex": filter_complex,
        "output_label": output_label,
        "final_video": final_v,
        "final_audio": final_a,
        "has_video": True,
        "has_audio": True,
    }


def _build_segment_filters(
    v_in: str,
    a_in: str,
    effects: list[dict],
    seg_idx: int,
    start: float,
    end: float,
) -> tuple[str, str]:
    """
    Build filter graph labels for a single segment after applying all effects.
    Returns (video_output_label, audio_output_label).
    """
    v_label = f"[sv{seg_idx}]"
    a_label = f"[sa{seg_idx}]"

    v_filters: list[str] = []
    a_filters: list[str] = []

    duration = end - start

    for eff in effects:
        if not eff.get("enabled", True):
            continue
        etype = eff.get("type", "")
        params = eff.get("params", {})
        
        # Defensive: ensure params is a dict
        if not isinstance(params, dict):
            logger.warning("Effect params is not a dict (got %s), using empty dict", type(params))
            params = {}

        if etype == EffectType.VOLUME:
            level = params.get("level", 1.0)
            a_filters.append(f"volume={level}")

        elif etype == EffectType.MUTE:
            a_filters.append("volume=0")

        elif etype == EffectType.FADE_IN:
            d = params.get("duration_s", 0.5)
            v_filters.append(f"fade=t=in:st=0:d={d}")
            a_filters.append(f"afade=t=in:st=0:d={d}")

        elif etype == EffectType.FADE_OUT:
            d = params.get("duration_s", 0.5)
            fade_start = max(0.0, duration - d)
            v_filters.append(f"fade=t=out:st={fade_start:.3f}:d={d}")
            a_filters.append(f"afade=t=out:st={fade_start:.3f}:d={d}")

        elif etype == EffectType.SPEED:
            factor = params.get("factor", 1.0)
            if factor != 1.0:
                v_filters.append(f"setpts={1.0 / factor:.4f}*PTS")
                a_filters.append(f"atempo={factor:.4f}")

        elif etype == EffectType.CROP:
            x = params.get("x", 0)
            y = params.get("y", 0)
            w = params.get("w", 1280)
            h = params.get("h", 720)
            v_filters.append(f"crop={w}:{h}:{x}:{y}")

        elif etype == EffectType.CAPTION:
            text = params.get("text", "").strip()
            # Skip caption if text is empty (happens when params is string/invalid)
            if not text:
                logger.warning("Caption effect has no text, skipping")
                continue
            # Escape special characters for FFmpeg
            text = text.replace("'", "\\'").replace(":", "\\:")
            v_filters.append(
                f"drawtext=text='{text}':fontsize=24:fontcolor=white"
                f":x=(w-text_w)/2:y=h-text_h-20:box=1:boxcolor=black@0.5"
            )

    # Assemble filter strings
    if v_filters:
        v_chain = f"{v_in}{','.join(v_filters)}{v_label}"
    else:
        # Use 'null' filter for passthrough (copy/acopy don't exist!)
        v_chain = f"{v_in}null{v_label}"

    if a_filters:
        a_chain = f"{a_in}{','.join(a_filters)}{a_label}"
    else:
        # Use 'anull' filter for audio passthrough
        a_chain = f"{a_in}anull{a_label}"

    return v_chain, a_chain


def _build_transitions(
    sequence: list[SequenceEntry],
    segment_pool: dict,
    edit_layers: dict,
    video_labels: list[str],
    audio_labels: list[str],
) -> tuple[list[str], str, str]:
    """
    Build transition filters between segments.
    Returns (filter_lines, final_video_label, final_audio_label).
    """
    filter_lines: list[str] = []

    if not video_labels:
        return [], "", ""

    if len(video_labels) == 1:
        return [], video_labels[0], audio_labels[0]

    # Precompute actual durations for each segment
    durations = []
    for entry in sequence:
        seg = segment_pool.get(entry.segment_id)
        if seg is None:
            durations.append(0.0)
            continue
            
        edit = edit_layers.get(entry.segment_id, {})
        trim = edit.get("trim", {})

        seg_start = seg["start"]
        seg_end = seg["end"]

        trim_start = trim.get("start") or 0.0
        trim_end = trim.get("end")

        actual_start = seg_start + trim_start
        actual_end = seg_end - trim_end if trim_end is not None else seg_end

        durations.append(actual_end - actual_start)

    # Build a list of (v_label, a_label, transition_in) for each segment
    entries_with_labels = []
    for i, entry in enumerate(sequence):
        entries_with_labels.append((
            video_labels[i] if i < len(video_labels) else None,
            audio_labels[i] if i < len(audio_labels) else None,
            entry.transition_in,
        ))

    # Track cumulative timeline duration
    timeline_duration = durations[0]
    
    current_v = entries_with_labels[0][0]
    current_a = entries_with_labels[0][1]
    merge_idx = 0

    for i in range(1, len(entries_with_labels)):
        v2, a2, transition = entries_with_labels[i]
        if v2 is None:
            continue

        out_v = f"[mv{merge_idx}]"
        out_a = f"[ma{merge_idx}]"
        merge_idx += 1

        if (
            transition is not None
            and transition.type in (TransitionType.CROSSFADE, TransitionType.DISSOLVE)
        ):
            d = transition.duration_s
            # xfade for video, acrossfade for audio
            xfade_mode = "dissolve" if transition.type == TransitionType.DISSOLVE else "fade"
            
            # CRITICAL FIX: Compute correct offset based on timeline duration
            offset = max(0.0, timeline_duration - d)
            
            filter_lines.append(
                f"{current_v}{v2}xfade=transition={xfade_mode}:duration={d}:offset={offset:.3f}{out_v}"
            )
            filter_lines.append(
                f"{current_a}{a2}acrossfade=d={d}{out_a}"
            )
            
            # Update timeline: new_length = prev_length + next_length - transition_duration
            timeline_duration = timeline_duration + durations[i] - d
        else:
            # Plain cut — concat
            filter_lines.append(
                f"{current_v}{v2}concat=n=2:v=1:a=0{out_v}"
            )
            filter_lines.append(
                f"{current_a}{a2}concat=n=2:v=0:a=1{out_a}"
            )
            
            # Update timeline: just add next segment duration
            timeline_duration += durations[i]

        current_v = out_v
        current_a = out_a

    return filter_lines, current_v, current_a
