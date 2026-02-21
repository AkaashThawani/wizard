# Wizard — Architecture

## Overview

Wizard is an AI-native video editor whose core is an **AI orchestration layer**. A user types a natural-language prompt; the orchestrator interprets it, selects appropriate agents, executes them against a shared state (the **blackboard**), and returns a result. All non-destructive mutations are logged; any failure triggers a full rollback.

---

## Orchestrator Flow

```
User prompt
    │
    ▼
1. intent_detector.scan(prompt)         ← keyword scan, no LLM, identifies likely agents
    │
    ▼
2. context_builder.build(state, agents)  ← lean context from TimelineState + agent summaries
    │
    ▼
3. llm_client.tool_call(system, prompt, registry.all_tools(), context)
   ← single LLM call; model picks tools + params via provider tool-calling API
    │
    ▼
4. Validate tool names against registry  ← reject unknown tools, no execution
    │
    ▼
5. state.take_snapshot()                ← pre-execution checkpoint
    │
    ▼
6. task_graph.build(tool_calls)         ← topological sort on depends_on → parallel groups
    │
    ▼
7. Execute groups with asyncio.gather   ← each parallel group runs concurrently
    │
    ├── ToolResult.success == False → state.rollback(snap_id), return error
    │
    ▼
8. state.add_history(prompt, summary)
    │
    ▼
9. Return OrchestratorResult
```

No 2-stage LLM calls. No separate intent-confirmation round-trip. One call; the model uses the registered tools directly.

---

## Agent Contract

Every agent implements `BaseAgent`:

```python
class BaseAgent(ABC):
    def __init__(self, state: TimelineState, config: dict): ...

    async def run(self, params: dict) -> AgentStatus:
        """Pipeline entry point — used for batch/pipeline operations."""

    def get_tools(self) -> list[Tool]:
        """Declares all tools this agent can execute. Called at registration time."""

    async def execute_tool(self, name: str, params: dict) -> ToolResult:
        """Dispatches a single tool call. Called by the orchestrator."""

    def get_lean_context(self) -> dict:
        """Compact dict summarising agent state for the LLM context."""

    def can_handle(self, tool_name: str) -> bool:
        """True if this agent owns the named tool."""

    def description(self) -> str:
        """One-line description of agent capabilities."""
```

### Tool Declaration

```python
@dataclass
class Tool:
    name: str           # "edit.remove_short"
    description: str    # LLM reads this to decide when to call it
    parameters: dict    # JSON Schema — {type, properties, required}
    depends_on: list[str] = field(default_factory=list)  # tool names this must follow
```

### Tool Result

```python
@dataclass
class ToolResult:
    success: bool
    data: dict          # returned to orchestrator / next tool in chain
    error: str | None
```

---

## Agent Registry

`AgentRegistry` is the single source of truth for which agents and tools are available.

```
register(agent)       → reads agent.get_tools() → maps tool_name → agent instance
all_tools()           → merged list of all Tool declarations → passed to LLM
get_agent(tool_name)  → agent instance
```

Adding a new agent = implement `BaseAgent`, call `registry.register(agent)` in `app.py`. Zero changes elsewhere.

---

## Timeline State (The Blackboard)

All agents share a single `TimelineState` object. Persisted to `projects/{project_id}/timeline.json` after every mutation.

### Structure

```json
{
  "source": {
    "path": "projects/{id}/source.mp4",
    "filename": "interview.mp4",
    "duration": 543.2
  },

  "segment_pool": {
    "{segment_id}": { "...Segment fields..." }
  },

  "layers": {
    "edit_agent": {
      "{segment_id}": {
        "trim": {"start": 0.0, "end": null},
        "effects": [
          {"type": "volume", "params": {"level": 0.8}, "enabled": true}
        ]
      }
    },
    "search_agent": {
      "{segment_id}": {"topics": [], "keywords": [], "summary": "..."}
    },
    "color_agent":  {"{segment_id}": {}},
    "audio_agent":  {"{segment_id}": {}}
  },

  "agent_data": {
    "search_agent": {"last_query": "...", "last_result_count": 4}
  },

  "snapshots": {
    "{snap_id}": {"sequence": [], "timestamp": "2024-01-01T12:00:00Z"}
  },

  "current": {
    "sequence": [
      {"segment_id": "seg_001", "transition_in": null},
      {"segment_id": "seg_007", "transition_in": {"type": "crossfade", "duration_s": 0.5}}
    ],
    "snapshot_ref": "{snap_id}"
  },

  "history": [
    {"prompt": "transcribe this video", "summary": "Transcribed 47 segments.", "snapshot_ref": "{snap_id}"}
  ]
}
```

### Key Properties

- `segment_pool` — append-only. Segments are never deleted; they are excluded from `current.sequence`.
- `layers` — each agent writes to its own namespace. No cross-agent writes.
- `current.sequence` — the actual edit: ordered list of segment IDs with optional transition metadata.
- `snapshots` — stored in the timeline; rollback = restore `current.sequence` from snapshot.

### LLM Context (lean)

`to_llm_context()` returns a compact dict — never sends full transcripts or embeddings to the LLM:

```python
{
  "source": {"filename": "interview.mp4", "duration": 543.2},
  "segment_count": 47,
  "current_segments": [
    {"id": "seg_001", "duration": 4.2, "text_preview": "So the main challenge was..."}
  ],                                                    # 150 char cap per preview
  "history": ["Transcribed 47 segments.", "Filtered to 12 mentions of ML."],  # last 5
  "agent_context": {
    "edit_agent":   {"cut_length_s": 38.4, "segment_count": 9, "last_op": "remove_short"},
    "search_agent": {"last_query": "machine learning", "result_count": 4, "top_ids": []}
  }
}
```

---

## Data Models

### WordToken
```python
@dataclass
class WordToken:
    word: str
    start: float      # seconds from video start
    end: float
    confidence: float  # 0.0–1.0 from Whisper
```

### Segment
```python
@dataclass
class Segment:
    id: str            # stable UUID, never changes
    start: float       # source timecode
    end: float
    duration: float
    text: str          # full sentence text
    words: list[WordToken]   # word-level — never sent to LLM
    speaker: str | None
    source: str        # path to source file
    chroma_id: str     # ID in chroma/text collection
```

Segments always start and end at **sentence boundaries** (enforced by chunker).
Trim points snap to nearest `WordToken`, preferring `confidence > 0.8`.

---

## Search Query Routing

```python
def query_mode(query: str) -> str:
    words = query.split()
    if len(words) <= 5 and not any(w in query for w in ["except", "but not", "and", "or"]):
        return "vector"    # ChromaDB similarity only
    return "hybrid"        # vector + Claude refinement pass
```

Word-count heuristic — no LLM call for routing.
Future: detect visual/audio keywords → route to `chroma/visual` or `chroma/audio`.

---

## ChromaDB Collections

Three named collections, all indexed by `segment_id`:

| Collection      | Embeddings                         | Status               |
|-----------------|------------------------------------|----------------------|
| `chroma/text`   | sentence-transformers (MiniLM-L6)  | Built in v1          |
| `chroma/visual` | CLIP (ViT-B/32)                    | Stubbed — ColorAgent |
| `chroma/audio`  | librosa feature vectors            | Stubbed — AudioAgent |

---

## Effects Model

Per-segment, non-destructive, lives in `layers["edit_agent"][segment_id].effects`:

```json
[
  {"type": "volume",   "params": {"level": 0.8},          "enabled": true},
  {"type": "fade_in",  "params": {"duration_s": 0.5},     "enabled": true},
  {"type": "fade_out", "params": {"duration_s": 0.5},     "enabled": true},
  {"type": "mute",     "params": {},                       "enabled": false},
  {"type": "caption",  "params": {"text": "Speaker 1"},   "enabled": true},
  {"type": "speed",    "params": {"factor": 1.5},          "enabled": true},
  {"type": "crop",     "params": {"x":0,"y":0,"w":1280,"h":720}, "enabled": true}
]
```

Transitions live in `current.sequence[i].transition_in`.
Trim points live in `layers["edit_agent"][segment_id].trim`.
`ExportAgent` compiles all layers → single FFmpeg `filter_complex` call via `media/effect_compiler.py`.

---

## Audio Data Pipeline

```
Whisper via ONNX Runtime (word_timestamps=True)
    │  list[WordToken]
    ▼
cleaner.py     ← remove fillers (um/uh/like), deduplicate repeated phrases
    │
    ▼
merger.py      ← merge adjacent segments separated by silence < 0.5s
    │
    ▼
chunker.py     ← sentence boundaries via punctuation + confidence scores
    │  sentence-aligned list[Segment]
    ▼
enricher.py    ← single LLM call → topics, keywords, summary per segment
    │           writes to layers["search_agent"]
    ▼
vectorizer.py  ← sentence-transformers → ChromaDB chroma/text
               writes chroma_id back to each Segment
```

`deepmultilingualpunctuation` is **not used** — Whisper output is already punctuated.

**Lazy model loading**: Whisper and sentence-transformers load on first use, cached in memory.

**Cross-platform**: ONNX Runtime automatically selects the best execution provider:
- Windows with NVIDIA GPU: CUDAExecutionProvider
- Mac with Apple Silicon: CoreMLExecutionProvider
- Fallback: CPUExecutionProvider
- No manual device detection required — works identically across platforms.

**RAM-based model selection**: Whisper model size is automatically selected based on available system RAM:
- 32GB+ → `large-v3` (best quality)
- 16GB+ → `small` (good quality, fast)
- 8GB+ → `base` (decent quality, faster)
- <8GB → `tiny` (minimal quality, fastest)

---

## LLM Client

Provider-agnostic wrapper. Provider selected from `config.json`:

```json
{"llm": {"provider": "anthropic", "model": "claude-sonnet-4-6"}}
```

Swapping to OpenAI = change config, zero code changes.

```python
class LLMClient:
    async def tool_call(system, user, tools, context) -> list[ToolCall]
    async def complete(system, user, context) -> str
```

Internal adapters: `_to_anthropic_tools()`, `_to_openai_tools()` — same external interface.

---

## Export

`ExportAgent` reads `current.sequence` + `layers["edit_agent"]` + `segment_pool`.
`media/effect_compiler.py` builds the FFmpeg `filter_complex` string.
Encoder selection: VideoToolbox (Mac) → h264_nvenc (Windows/NVIDIA) → libx264 (fallback).
Preview = 720p; full = source resolution.

---

## SSE Progress Streaming

`BaseAgent` accepts an optional `progress_callback(event: str, data: dict)`.
Flask `/project/<id>/stream` SSE endpoint pushes progress events to browser.
Demo feels responsive even during long Whisper transcription.

---

## Extensibility

To add a new modality (e.g. colour analysis):

1. Un-stub `agents/color_agent.py` — implement `execute_tool`
2. `registry.register(ColorAgent(...))` in `app.py` — one line
3. SearchAgent picks up `chroma/visual` automatically via keyword routing
4. Zero changes to orchestrator, timeline, or other agents
