# Wizard — Implementation Sequence

Each step has a clear done criterion. Steps build on each other; earlier steps must pass their done criterion before proceeding to the next.

---

## Step 0 — Documentation

Update ARCHITECTURE.md, FILE_STRUCTURE.md, SEQUENCE.md to reflect all planning decisions.

**Done:** Docs describe single-LLM tool-calling flow, updated Segment schema (WordToken + chroma_id), updated TimelineState structure, effects/transitions model, ChromaDB collections, pipeline without punctuator.

---

## Step 1 — Timeline Data Model

**Files:** `timeline/schema.py`, `timeline/models.py`, `timeline/__init__.py`

- `schema.py`: `TimelineKeys` string constants, `AGENT_OWNS` map, `EffectType` enum, `TransitionType` enum
- `models.py`: `WordToken`, `Segment`, `SequenceEntry`, `Transition`, `Effect`, `EditLayer`, `Snapshot`, `HistoryEntry` dataclasses

**Done:** `from timeline.models import Segment, WordToken` imports cleanly. All dataclasses round-trip through `json.dumps(dataclasses.asdict(...))` without error.

---

## Step 2 — TimelineState (The Blackboard)

**File:** `timeline/state.py`

Key methods:
- `__init__(project_id)` — load or create `projects/{id}/timeline.json`
- `add_segment(segment)` — append to segment_pool only
- `get_current_sequence()` → list[SequenceEntry]
- `set_sequence(entries)` — replaces `current.sequence`
- `get_layer(agent_name, segment_id)` → dict
- `set_layer(agent_name, segment_id, data)`
- `take_snapshot()` → snap_id
- `rollback(snap_id)`
- `record_error(agent_name, message)`
- `to_llm_context(agent_names)` → compact dict (150-char text previews, last 5 history)
- `save()` / `load()`

**Done:** Create state, add 3 segments, take snapshot, mutate sequence, rollback — sequence matches pre-mutation state. All round-trips through JSON without data loss.

---

## Step 3 — Agent Contract

**Files:** `agents/base.py`, `agents/registry.py`, `agents/__init__.py`

- `Tool`, `ToolResult`, `AgentStatus` dataclasses/enums in `base.py`
- `BaseAgent` ABC with all 6 methods
- `AgentRegistry` — register, get_agent, all_tools

**Done:** Register two dummy agents, assert `registry.get_agent("dummy.tool_a")` returns correct agent, assert `registry.all_tools()` returns merged list with all tools from both agents.

---

## Step 4 — LLM Client

**Files:** `llm/client.py`, `llm/prompts.py`, `llm/__init__.py`

- `LLMClient(provider, model, api_key)` — reads from config
- `async tool_call(system, user, tools, context)` → list[ToolCall]
- `async complete(system, user, context)` → str
- `_to_anthropic_tools(tools)` → Anthropic-format list
- `_to_openai_tools(tools)` → OpenAI-format list
- `prompts.py` — `ORCHESTRATOR_SYSTEM`, `SEARCH_REFINEMENT`, `ENRICHMENT`

**Done:** `LLMClient.tool_call()` makes a real call to Anthropic, returns at least one `ToolCall` when given a tool that matches the prompt.

---

## Step 5 — Audio Data Pipeline

**Files:** `pipeline/cleaner.py`, `pipeline/merger.py`, `pipeline/chunker.py`, `pipeline/enricher.py`, `pipeline/vectorizer.py`

- `cleaner.py` — remove fillers (um/uh/like), deduplicate
- `merger.py` — merge adjacent segments with silence < threshold
- `chunker.py` — sentence-boundary detection (punctuation + confidence > 0.8)
- `enricher.py` — single LLM call for entire transcript → per-segment metadata
- `vectorizer.py` — sentence-transformers lazy load → ChromaDB chroma/text

**Done:** Run pipeline on a short hardcoded transcript string. Assert: segments align to sentence boundaries. Assert: ChromaDB `chroma/text` collection contains correct number of entries. Assert: each Segment has a non-empty `chroma_id`.

---

## Step 6 — Agents (Working)

### Task 6a — TranscriptionAgent

`agents/transcription_agent.py`:
- faster-whisper, `device="auto"` (MPS/CUDA/CPU)
- `word_timestamps=True`
- Runs full pipeline: transcribe → clean → merge → chunk → enrich → vectorize
- Progress callback at each stage
- Tool: `transcription.transcribe`

**MILESTONE — Run on real video:**
- Upload a 5–15 min interview/talk video
- Send `"transcribe this video"` prompt
- Assert: segment_pool populated, each segment has WordToken list, chroma/text populated
- Assert: GUI shows all segments

### Task 6b — SearchAgent

`agents/search_agent.py`:
- `query_mode()` heuristic → "vector" or "hybrid"
- Vector: ChromaDB similarity, expand to neighboring chunks (window=1), add 0.5s padding
- Hybrid: vector results → LLMClient.complete() refinement
- Tools: `search.find_segments`

### Task 6c — EditAgent

`agents/edit_agent.py`:
- Pure Python, no ML, no LLM
- Tools: `edit.keep_only`, `edit.remove_short`, `edit.reorder`, `edit.set_transition`, `edit.trim_segment`, `edit.add_effect`
- Trim snaps to nearest WordToken (prefers confidence > 0.8)

### Task 6d — ExportAgent

`agents/export_agent.py`:
- Reads sequence + layers → `effect_compiler.compile()` → FFmpeg
- Preview at 720p, full at source resolution
- Tool: `export.export`

### Task 6e — ColorAgent (STUB)

`agents/color_agent.py`:
- Full BaseAgent interface implemented
- `execute_tool()` logs stub message, writes empty placeholder to layers["color_agent"]
- Tool: `color.analyze`

### Task 6f — AudioAgent (STUB)

`agents/audio_agent.py`:
- Full BaseAgent interface implemented
- `execute_tool()` logs stub message, writes empty placeholder to layers["audio_agent"]
- Tool: `audio.analyze`

**Done (Step 6):** Full chain on real video — transcription → search → edit → export produces playable MP4.

---

## Step 7 — Media Layer

**Files:** `media/video_info.py`, `media/effect_compiler.py`, `media/ffmpeg_wrapper.py`

- `video_info.get_info(path)` → {duration, fps, width, height, has_audio}
- `effect_compiler.compile(sequence, layers, pool)` → FFmpeg filter_complex string
- `ffmpeg_wrapper.cut()`, `export()`, `detect_encoder()`, `extract_frame()`

**Done:** `effect_compiler.compile()` with a 3-segment sequence + volume effect produces a valid filter_complex string. `ffmpeg_wrapper.detect_encoder()` returns one of the three valid encoder strings.

---

## Step 8 — Orchestrator

**Files:** `orchestrator/intent_detector.py`, `orchestrator/context_builder.py`, `orchestrator/task_graph.py`, `orchestrator/orchestrator.py`

- `intent_detector.scan(prompt)` → set[str] of agent names (keyword-only, no LLM)
- `ContextAssembler.build(state, agent_names)` → LLM-ready dict
- `TaskGraph.build(tool_calls)` → parallel groups (list[list[ToolCall]])
- `Orchestrator.handle_prompt(prompt)` → full 9-step flow

**Done:** Two sequential prompts on same state — second prompt sees mutations from first. Unknown tool name rejected before execution. Failed tool triggers rollback.

---

## Step 9 — Flask Server

**File:** `app.py`

Routes:
- `POST /project` — create project, return project_id
- `POST /project/<id>/upload` — save video to `projects/{id}/source.mp4`
- `POST /project/<id>/prompt` — run Orchestrator, return JSON result
- `GET  /project/<id>/timeline` — return current state for GUI
- `GET  /project/<id>/stream` — SSE endpoint, streams agent progress events
- `GET  /project/<id>/export/<filename>` — serve exported video

**Done:** All routes respond. SSE endpoint delivers at least one event during a transcription run.

---

## Step 10 — GUI

**Files:** `gui/templates/index.html`, `gui/static/app.js`, `gui/static/style.css`

Layout:
- Left: video player (source or last export)
- Centre: timeline — horizontal segment blocks coloured by agent annotations, click to preview
- Right: prompt input + response area, history list
- Bottom: export button, progress bar from SSE

**Done:** Full end-to-end demo in browser — transcribe → search → edit → export, with visual timeline updates after each prompt.

---

## Step 11 — Demo Script

**Prompt 1:** `"transcribe this video"`
→ TranscriptionAgent runs full pipeline
→ Timeline shows all sentence-aligned segments

**Prompt 2:** `"pull every mention of [topic] into a sequence"`
→ SearchAgent + EditAgent → filtered sequence
→ ExportAgent → preview cut

**Prompt 3:** `"remove any clip under 3 seconds and add 0.5s crossfades"`
→ EditAgent.remove_short + set_transition per boundary
→ ExportAgent → crossfaded export

All three prompts on same TimelineState. Snapshots exist for each. Demo shows rollback to Prompt 1 state.

---

## End-to-End Verification Checklist

- [ ] `python app.py` starts with no model loading (lazy load)
- [ ] Upload video via GUI
- [ ] "transcribe" → segments appear in GUI
- [ ] Search prompt → timeline filtered
- [ ] Edit prompt → segments removed, transitions set
- [ ] Export → playable MP4 served by Flask
- [ ] Second edit → mutations stack correctly
- [ ] Rollback to earlier snapshot → sequence restored

## Cross-Platform Check

- Mac: `device="auto"` → MPS, `detect_encoder()` → VideoToolbox
- Windows: `device="auto"` → CUDA/CPU, `detect_encoder()` → h264_nvenc / libx264
- Platform conditionals only in `detect_encoder()` and Whisper device selection
