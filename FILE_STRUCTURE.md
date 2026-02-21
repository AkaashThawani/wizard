# Wizard — File Structure

```
D:\wizard\
├── ARCHITECTURE.md          ← system design and data models
├── FILE_STRUCTURE.md        ← this file
├── SEQUENCE.md              ← implementation sequence with done criteria
├── requirements.txt         ← all dependencies
├── config.json              ← provider, model, pipeline settings
├── app.py                   ← Flask server; /stream SSE endpoint for progress
│
├── timeline/
│   ├── __init__.py
│   ├── schema.py            ← TimelineKeys constants, AGENT_OWNS map, EffectType/TransitionType enums
│   ├── models.py            ← WordToken, Segment, SequenceEntry, Transition, Effect, EditLayer,
│   │                           Snapshot, HistoryEntry dataclasses
│   └── state.py             ← TimelineState blackboard; load/save/snapshot/rollback/to_llm_context
│
├── agents/
│   ├── __init__.py
│   ├── base.py              ← Tool, ToolResult, AgentStatus, BaseAgent ABC
│   ├── registry.py          ← AgentRegistry; register/get_agent/all_tools
│   ├── transcription_agent.py  ← faster-whisper; runs full pipeline; tool: transcription.transcribe
│   ├── search_agent.py      ← ChromaDB similarity + hybrid LLM refinement; tools: search.find_segments
│   ├── edit_agent.py        ← pure Python, no ML; tools: edit.keep_only, remove_short, reorder,
│   │                           set_transition, trim_segment, add_effect
│   ├── export_agent.py      ← reads layers → effect_compiler → FFmpeg; tool: export.export
│   ├── color_agent.py       ← STUB: interface for CLIP visual embeddings; tool: color.analyze
│   └── audio_agent.py       ← STUB: interface for librosa audio features; tool: audio.analyze
│
├── llm/
│   ├── __init__.py
│   ├── client.py            ← LLMClient; provider-agnostic; tool_call() / complete()
│   └── prompts.py           ← ORCHESTRATOR_SYSTEM, SEARCH_REFINEMENT, ENRICHMENT templates
│
├── pipeline/
│   ├── __init__.py
│   ├── cleaner.py           ← remove filler words, deduplicate repeated phrases
│   ├── merger.py            ← merge adjacent segments separated by short silences
│   ├── chunker.py           ← sentence-boundary detection using punctuation + confidence
│   ├── enricher.py          ← single LLM call → topics/keywords/summary per segment
│   └── vectorizer.py        ← sentence-transformers → ChromaDB chroma/text; lazy model load
│
├── media/
│   ├── __init__.py
│   ├── video_info.py        ← ffprobe wrapper; get_info() → {duration, fps, width, height, has_audio}
│   ├── effect_compiler.py   ← compile(sequence, layers, segment_pool) → FFmpeg filter_complex string
│   └── ffmpeg_wrapper.py    ← cut(), export(), detect_encoder(), extract_frame()
│
├── orchestrator/
│   ├── __init__.py
│   ├── intent_detector.py   ← keyword scan (no LLM); returns likely agent names from prompt
│   ├── context_builder.py   ← ContextAssembler.build(state, agent_names) → LLM-ready dict
│   ├── task_graph.py        ← parse tool calls → topological sort → parallel execution groups
│   └── orchestrator.py      ← Orchestrator.handle_prompt(); full 9-step flow
│
├── projects/
│   └── {project_id}/
│       ├── timeline.json    ← blackboard, persisted to disk after every mutation
│       ├── source.mp4       ← original upload
│       ├── exports/         ← FFmpeg output files
│       └── chroma/
│           ├── text/        ← ChromaDB collection: sentence-transformer embeddings
│           ├── visual/      ← ChromaDB collection: CLIP embeddings (populated by ColorAgent)
│           └── audio/       ← ChromaDB collection: librosa feature vectors (populated by AudioAgent)
│
└── gui/
    ├── templates/
    │   └── index.html       ← single-page app shell
    └── static/
        ├── app.js           ← timeline renderer, SSE listener, prompt dispatcher
        └── style.css        ← dark theme, monospace font
```

## Removed

- `pipeline/punctuator.py` — removed. Whisper output is already punctuated. `deepmultilingualpunctuation` is not a dependency.

## Stubbed (clear interface notes in source)

- `agents/color_agent.py` — CLIP + FFmpeg keyframe extraction + `chroma/visual`
- `agents/audio_agent.py` — librosa feature extraction + `chroma/audio`

## Notes

- `projects/` directory is created at runtime by `app.py` when a new project is initialised.
- ChromaDB stores its data on disk inside `projects/{id}/chroma/` — one persistent client per project.
- All agent writes go to `state.layers[agent_name]` — no direct file I/O from agents (except ExportAgent for the final video).
- `config.json` selects LLM provider/model; swapping provider requires no code changes.
