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

    segment_ids = list(payload.keys())
    logger.info("=" * 70)
    logger.info("🔍 ENRICHMENT BATCH START")
    logger.info("  Segments in batch: %d", len(segments))
    logger.info("  Segment IDs: %s", segment_ids[:3] + ["..."] if len(segment_ids) > 3 else segment_ids)
    logger.info("  Total text length: %d chars", sum(len(s.text) for s in segments))
    logger.info("=" * 70)

    user_message = (
        "Analyse the following transcript segments and return the JSON "
        "metadata object as described.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        print("\n" + "="*70)
        print("📤 GEMINI API CALL - Sending enrichment request...")
        print(f"  Prompt length: {len(user_message)} chars")
        print(f"  Batch size: {len(segments)} segments")
        print("="*70)
        
        logger.info("📤 Sending LLM request for enrichment...")
        logger.info("  Prompt length: %d chars", len(user_message))
        
        import time
        start_time = time.time()
        
        print(f"⏱️  Starting Gemini call at {time.time()}")
        raw = await llm_client.complete(
            system=ENRICHMENT,
            user=user_message,
        )
        print(f"✅ Gemini call completed at {time.time()}")
        
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print(f"📥 GEMINI RESPONSE RECEIVED ({elapsed:.2f} seconds)")
        print(f"  Response length: {len(raw)} chars")
        print(f"  Response preview: {raw[:200]}...")
        print("="*70 + "\n")
        
        logger.info("📥 LLM response received (%.2f seconds)", elapsed)
        logger.info("  Response length: %d chars", len(raw))
        
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]

        logger.info("🔄 Parsing JSON response...")
        result: dict = json.loads(raw)
        logger.info("✓ JSON parsed successfully - %d segment entries", len(result))

    except Exception as exc:
        logger.warning("❌ Enrichment LLM call failed: %s — using empty metadata", exc)
        logger.warning("  Raw response (first 500 chars): %s", raw[:500] if 'raw' in locals() else "N/A")
        result = {}

    logger.info("💾 Storing enrichment data in state layers...")
    for seg in segments:
        metadata = result.get(seg.id, {})
        state.set_layer("search_agent", seg.id, {
            "topics": metadata.get("topics", []),
            "keywords": metadata.get("keywords", []),
            "summary": metadata.get("summary", ""),
        })
    
    logger.info("=" * 70)
    logger.info("✅ ENRICHMENT BATCH COMPLETE")
    logger.info("  Segments processed: %d/%d", len([r for r in result.values() if r]), len(segments))
    logger.info("=" * 70)
