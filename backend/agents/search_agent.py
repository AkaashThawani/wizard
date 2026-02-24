"""
agents/search_agent.py

SearchAgent — finds segments by semantic similarity.

Query routing (word-count heuristic, no LLM call):
  ≤5 words, no boolean operators → vector-only (ChromaDB)
  >5 words or boolean operators  → hybrid (vector + Claude refinement)

Vector search:
  - ChromaDB chroma/text similarity search
  - Expands results to include neighboring chunks (window=1)
  - Adds 0.5s padding to start/end

Hybrid search:
  - Vector results → LLMClient.complete() refinement pass
  - Claude reads candidate texts and returns only the relevant segment IDs

STUB NOTE: visual and audio collection queries go here when ColorAgent/AudioAgent
are registered and their collections are populated.

Tools:
  search.find_segments {query: str, max_results: int}
"""

from __future__ import annotations

import json
import logging
from agents.base import BaseAgent, Tool, ToolResult, AgentStatus
from llm.prompts import SEARCH_REFINEMENT

logger = logging.getLogger(__name__)

PADDING = 0.5        # seconds added to each side of search results
NEIGHBOR_WINDOW = 0  # expand each result to ±N neighboring segments (0 = exact matches only)
BOOLEAN_MARKERS = {"except", "but not", "and", "or", "not", "without"}


def query_mode(query: str) -> str:
    """
    Word-count heuristic — no LLM call.

    Returns "vector" or "hybrid".
    """
    words = query.lower().split()
    if len(words) <= 5 and not any(w in BOOLEAN_MARKERS for w in words):
        return "vector"
    return "hybrid"


class SearchAgent(BaseAgent):
    """
    Semantic search over the segment pool.

    Uses ChromaDB for vector similarity and (optionally) Claude for refinement.
    """

    def __init__(self, state, config, llm_client=None, progress_callback=None):
        super().__init__(state, config, progress_callback)
        self._llm_client = llm_client
        self._last_query: str = ""
        self._last_result_ids: list[str] = []

    def description(self) -> str:
        return "Searches transcript segments by semantic similarity."

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="search_find_segments",
                description=(
                    "Find transcript segments that match a natural-language query. "
                    "Returns a list of segment IDs ordered by relevance. "
                    "Use this to identify which segments talk about a topic before editing."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language search query",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            )
        ]

    async def run(self, params: dict) -> AgentStatus:
        result = await self.execute_tool("search_find_segments", params)
        return AgentStatus.SUCCESS if result.success else AgentStatus.FAILED

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        if name != "search_find_segments":
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        query = params.get("query", "").strip()
        
        # Handle max_results - if None or not provided, return all results
        max_results_param = params.get("max_results")
        if max_results_param is None:
            max_results = None  # Return all results
        else:
            max_results = int(max_results_param)

        if not query:
            return ToolResult(success=False, data={}, error="query is required")

        try:
            return await self._search(query, max_results)
        except Exception as exc:
            logger.exception("Search failed: %s", exc)
            return ToolResult(success=False, data={}, error=str(exc))

    async def _search(self, query: str, max_results: int | None) -> ToolResult:
        from pipeline.vectorizer import similarity_search

        self._emit("stage", {"stage": "search", "status": "running", "query": query})

        mode = query_mode(query)
        logger.info("Search mode: %s for query: '%s'", mode, query)

        # Vector search with similarity threshold filtering
        raw_results = similarity_search(query, self.state, n_results=100)  # Get all potential matches
        
        # Filter by similarity threshold (distance < 0.7 means more similar - relaxed for better recall)
        SIMILARITY_THRESHOLD = 0.7
        filtered_results = [r for r in raw_results if r.get("distance", 1.0) < SIMILARITY_THRESHOLD]
        
        if not filtered_results:
            self._emit("stage", {"stage": "search", "status": "done", "count": 0})
            return ToolResult(
                success=True,
                data={"segment_ids": [], "query": query, "mode": mode},
            )

        # Expand with neighboring chunks
        all_segment_ids = list(self.state.get_all_segments().keys())
        expanded_ids = self._expand_neighbors(
            [r["id"] for r in filtered_results], all_segment_ids
        )

        # For vector mode: just return expanded results
        if mode == "vector" or self._llm_client is None:
            result_ids = expanded_ids[:max_results]
            self._update_agent_data(query, result_ids)
            
            # Update current_sequence to show only search results
            self._update_sequence(result_ids)
            
            self._emit("stage", {"stage": "search", "status": "done", "count": len(result_ids)})
            
            # Include full text of found segments
            segments = self.state.get_all_segments()
            full_text = self._build_text_display(result_ids, segments)
            
            return ToolResult(
                success=True,
                data={"segment_ids": result_ids, "query": query, "mode": mode, "full_text": full_text},
            )

        # Hybrid: refine with Claude
        result_ids = await self._refine_with_llm(query, expanded_ids, max_results)
        self._update_agent_data(query, result_ids)
        
        # Update current_sequence to show only search results
        self._update_sequence(result_ids)
        
        self._emit("stage", {"stage": "search", "status": "done", "count": len(result_ids)})
        
        # Include full text of found segments
        segments = self.state.get_all_segments()
        full_text = self._build_text_display(result_ids, segments)

        return ToolResult(
            success=True,
            data={"segment_ids": result_ids, "query": query, "mode": mode, "full_text": full_text},
        )

    def _expand_neighbors(
        self,
        result_ids: list[str],
        all_ids: list[str],
    ) -> list[str]:
        """Expand each result to include ±NEIGHBOR_WINDOW neighboring segments."""
        result_set = set(result_ids)
        expanded: list[str] = []
        seen: set[str] = set()

        for seg_id in result_ids:
            if seg_id not in all_ids:
                continue
            idx = all_ids.index(seg_id)
            start = max(0, idx - NEIGHBOR_WINDOW)
            end = min(len(all_ids) - 1, idx + NEIGHBOR_WINDOW)

            for i in range(start, end + 1):
                neighbor_id = all_ids[i]
                if neighbor_id not in seen:
                    expanded.append(neighbor_id)
                    seen.add(neighbor_id)

        return expanded

    async def _refine_with_llm(
        self,
        query: str,
        candidate_ids: list[str],
        max_results: int | None,
    ) -> list[str]:
        """Use Claude to filter candidate segments to only relevant ones."""
        segments = self.state.get_all_segments()

        candidates = []
        for seg_id in candidate_ids:
            seg = segments.get(seg_id)
            if seg:
                candidates.append({"id": seg_id, "text": seg.text[:300]})

        user_message = (
            f"User query: {query}\n\n"
            f"Candidate segments:\n{json.dumps(candidates, indent=2)}"
        )

        try:
            raw = await self._llm_client.complete(
                system=SEARCH_REFINEMENT,
                user=user_message,
            )
            result = json.loads(raw)
            ids = result.get("segment_ids", [])
            # Handle None - return all results if max_results is None
            filtered = [sid for sid in ids if sid in {c["id"] for c in candidates}]
            return filtered if max_results is None else filtered[:max_results]
        except Exception as exc:
            logger.warning("LLM refinement failed: %s — falling back to vector results", exc)
            return candidate_ids if max_results is None else candidate_ids[:max_results]

    def _build_text_display(self, segment_ids: list[str], segments: dict) -> str:
        """Build formatted text display of found segments."""
        lines = []
        for i, seg_id in enumerate(segment_ids, 1):
            seg = segments.get(seg_id)
            if seg:
                lines.append(f"[{i}] {seg.text}")
        return "\n\n".join(lines) if lines else "No segments found."

    def _update_sequence(self, segment_ids: list[str]) -> None:
        """Update current_sequence to show only search results."""
        from timeline.models import SequenceEntry
        
        # Deduplicate segment IDs while preserving order
        unique_ids = list(dict.fromkeys(segment_ids))
        
        # Sort segment IDs by start time to ensure proper playback order
        segments = self.state.get_all_segments()
        sorted_ids = sorted(unique_ids, key=lambda sid: segments[sid].start if sid in segments else 0)
        
        # Create new sequence from sorted search results
        sequence = [SequenceEntry(segment_id=sid, transition_in=None) for sid in sorted_ids]
        self.state.set_sequence(sequence)
        logger.info("Updated sequence to %d unique search results (sorted by time)", len(sorted_ids))

    def _update_agent_data(self, query: str, result_ids: list[str]) -> None:
        self._last_query = query
        self._last_result_ids = result_ids
        self.state.set_agent_data("search_agent", {
            "last_query": query,
            "last_result_count": len(result_ids),
            "top_ids": result_ids[:5],
        })

    def get_lean_context(self) -> dict:
        data = self.state.get_agent_data("search_agent")
        return {
            "last_query": data.get("last_query", ""),
            "result_count": data.get("last_result_count", 0),
            "top_ids": data.get("top_ids", []),
        }
