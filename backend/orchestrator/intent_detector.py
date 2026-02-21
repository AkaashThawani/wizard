"""
orchestrator/intent_detector.py

Keyword-based intent detection — no LLM call, instant.

Scans the user prompt for keywords associated with each agent and returns
the set of agent names likely needed to handle the prompt.

Used by context_builder to include only relevant agent lean_contexts
in the LLM system message, keeping the context lean.
"""

from __future__ import annotations

import re


# Keyword → agent name mapping
# Each entry: (regex_pattern, agent_name)
# Patterns are case-insensitive.

_INTENT_RULES: list[tuple[str, str]] = [
    # Transcription
    (r"\btranscri(be|ption|pt)\b", "transcription_agent"),
    (r"\b(whisper|speech.to.text|voice.to.text)\b", "transcription_agent"),
    (r"\b(listen|process audio|analyse speech)\b", "transcription_agent"),

    # Search / find
    (r"\b(find|search|look for|show me|pull|get|fetch|where|mentions?|talks? about)\b", "search_agent"),
    (r"\b(about|regarding|related to|involving|covering)\b", "search_agent"),
    (r"\b(every|all)\s+(segment|clip|part|moment|instance|time)\b", "search_agent"),

    # Edit
    (r"\b(edit|cut|trim|remove|delete|keep|filter|reorder|rearrange|sort)\b", "edit_agent"),
    (r"\b(short(er)?|long(er)?|under|over|less than|more than)\s+\d+\s*s(ec(ond)?s?)?\b", "edit_agent"),
    (r"\b(transition|crossfade|dissolve|fade)\b", "edit_agent"),
    (r"\b(effect|volume|mute|caption|speed|crop)\b", "edit_agent"),
    (r"\b(sequence|order|timeline)\b", "edit_agent"),

    # Export
    (r"\b(export|render|compile|output|save|download|produce|generate.*(video|mp4|file))\b", "export_agent"),
    (r"\b(preview|full.res(olution)?|720p|1080p)\b", "export_agent"),

    # Color / visual
    (r"\b(color|colour|visual|bright|dark|scene|shot|frame|clip.look)\b", "color_agent"),
    (r"\b(palette|hue|saturation|contrast|lighting)\b", "color_agent"),

    # Audio features
    (r"\b(loud|quiet|energy|pitch|speech.rate|fast speech|slow speech)\b", "audio_agent"),
    (r"\b(audio.feature|sound.level|volume.level)\b", "audio_agent"),
]

_COMPILED_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), agent)
    for pattern, agent in _INTENT_RULES
]

# Agents that are almost always relevant (lightweight to include)
_ALWAYS_INCLUDE = {"edit_agent"}


def scan(prompt: str) -> set[str]:
    """
    Scan a prompt for intent keywords.

    Returns a set of agent names likely needed to handle the prompt.
    Always includes edit_agent (cheap context, almost always relevant).

    Example:
        scan("find all mentions of machine learning and cut the rest")
        → {"search_agent", "edit_agent"}
    """
    detected: set[str] = set(_ALWAYS_INCLUDE)

    for pattern, agent_name in _COMPILED_RULES:
        if pattern.search(prompt):
            detected.add(agent_name)

    return detected


def scan_with_explanation(prompt: str) -> dict:
    """
    Debug version — returns agents and the keywords that triggered each one.
    """
    detected: dict[str, list[str]] = {}

    for pattern, agent_name in _COMPILED_RULES:
        matches = pattern.findall(prompt)
        if matches:
            if agent_name not in detected:
                detected[agent_name] = []
            detected[agent_name].extend(matches)

    # Always include edit_agent
    if "edit_agent" not in detected:
        detected["edit_agent"] = ["(always included)"]

    return detected
