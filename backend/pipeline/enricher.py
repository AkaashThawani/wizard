"""
pipeline/enricher.py

Single LLM call to extract topics, keywords, and summaries for all segments.

Writes results to state.layers["search_agent"][segment_id].
"""

from __future__ import annotations

import json
import logging
from timeline.models import Segment
from llm.prompts import ENRICHMENT

logger = logging.getLogger(__name__)


async def enrich_segments(
    segments: list[Segment],
    llm_client,
    state,
    batch_size: int = 20,
) -> None:
    """
    Enrich all segments with topics, keywords, and summaries.

    Uses a single LLM call per batch (default: 20 segments).
    Writes results to state.layers["search_agent"][segment_id].

    Args:
        segments: List of Segment objects to enrich.
        llm_client: LLMClient instance.
        state: TimelineState instance.
        batch_size: Number of segments per LLM call (keep small to avoid
                    token-limit issues on very long transcripts).
    """
    for i in range(0, len(segments), batch_size):
        batch = segments[i:i + batch_size]
        await _enrich_batch(batch, llm_client, state)


async def _enrich_batch(
    segments: list[Segment],
    llm_client,
    state,
) -> None:
    # Build prompt payload — only text, no word-level data
    payload = {
        seg.id: {"text": seg.text[:500]}   # cap to avoid large prompts
        for seg in segments
    }

    user_message = (
        "Analyse the following transcript segments and return the JSON "
        "metadata object as described.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        raw = await llm_client.complete(
            system=ENRICHMENT,
            user=user_message,
        )
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]

        result: dict = json.loads(raw)

    except Exception as exc:
        logger.warning("Enrichment LLM call failed: %s — using empty metadata", exc)
        result = {}

    for seg in segments:
        metadata = result.get(seg.id, {})
        state.set_layer("search_agent", seg.id, {
            "topics": metadata.get("topics", []),
            "keywords": metadata.get("keywords", []),
            "summary": metadata.get("summary", ""),
        })
