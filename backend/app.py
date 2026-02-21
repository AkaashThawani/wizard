"""
app.py — Wizard Flask server

Routes:
  POST /project                           — create project, return project_id
  POST /project/<id>/upload               — upload source video
  POST /project/<id>/prompt               — send prompt to Orchestrator
  GET  /project/<id>/timeline             — return current timeline state
  GET  /project/<id>/stream               — SSE progress stream
  GET  /project/<id>/export/<filename>    — serve exported video

Design:
  - Lazy model loading: no models load at startup.
  - One Orchestrator per project (cached in _projects dict).
  - SSE endpoint uses a per-project event queue.
  - All business logic lives in agents and orchestrator — routes are thin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
load_dotenv()  # loads .env from project root before anything else

from flask import Flask, Response, jsonify, request, send_file, stream_with_context
from flask_cors import CORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    CONFIG = json.load(_f)

PROJECTS_DIR = Path(__file__).parent.parent / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# Application state (in-memory, per-process)
# ------------------------------------------------------------------

# project_id → {"state": TimelineState, "orchestrator": Orchestrator, "sse_queue": queue.Queue}
_projects: dict[str, dict] = {}

# ------------------------------------------------------------------
# Flask app
# ------------------------------------------------------------------

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])  # Allow Vite dev server


# ------------------------------------------------------------------
# Helper: get or create project context
# ------------------------------------------------------------------

def _get_project(project_id: str) -> dict | None:
    return _projects.get(project_id)


def _create_project_context(project_id: str) -> dict:
    from timeline.state import TimelineState
    from agents.registry import AgentRegistry
    from agents.transcription_agent import TranscriptionAgent
    from agents.search_agent import SearchAgent
    from agents.edit_agent import EditAgent
    from agents.export_agent import ExportAgent
    from agents.color_agent import ColorAgent
    from agents.audio_agent import AudioAgent
    from llm.client import LLMClient
    from orchestrator.orchestrator import Orchestrator

    # SSE queue — progress events are pushed here by agents
    sse_q: queue.Queue = queue.Queue()

    def progress_callback(event: str, data: dict) -> None:
        payload = json.dumps({"event": event, "data": data})
        sse_q.put_nowait(payload)

    state = TimelineState(project_id, projects_dir=str(PROJECTS_DIR))

    # LLM client
    llm_config = CONFIG.get("llm", {})
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    llm_client = LLMClient(
        provider=llm_config.get("provider", "anthropic"),
        model=llm_config.get("model", "claude-sonnet-4-6"),
        api_key=api_key,
    )

    # Build agents with shared config + progress callback
    agent_config = {
        **CONFIG,
        "whisper_model": CONFIG.get("whisper", {}).get("model_size", "base"),
    }

    transcription_agent = TranscriptionAgent(state, agent_config, progress_callback)
    search_agent = SearchAgent(state, agent_config, llm_client, progress_callback)
    edit_agent = EditAgent(state, agent_config, progress_callback)
    export_agent = ExportAgent(state, agent_config, progress_callback)
    color_agent = ColorAgent(state, agent_config, progress_callback)
    audio_agent = AudioAgent(state, agent_config, progress_callback)

    registry = AgentRegistry()
    registry.register(transcription_agent)
    registry.register(search_agent)
    registry.register(edit_agent)
    registry.register(export_agent)
    registry.register(color_agent)
    registry.register(audio_agent)

    orchestrator = Orchestrator(registry, llm_client, state)

    ctx = {
        "state": state,
        "orchestrator": orchestrator,
        "sse_queue": sse_q,
    }
    _projects[project_id] = ctx
    return ctx


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/project", methods=["POST"])
def create_project():
    """Create a new project. Returns project_id."""
    project_id = str(uuid.uuid4())[:8]
    _create_project_context(project_id)
    logger.info("Created project: %s", project_id)
    return jsonify({"project_id": project_id})


@app.route("/project/<project_id>/upload", methods=["POST"])
def upload_video(project_id: str):
    """Upload source video. Saves to projects/{id}/source.mp4."""
    ctx = _get_project(project_id)
    if ctx is None:
        ctx = _create_project_context(project_id)

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No filename"}), 400

    state = ctx["state"]
    dest = state.project_dir / "source.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    file.save(str(dest))

    # Probe video info
    try:
        from media.video_info import get_info
        info = get_info(str(dest))
        state.set_source(str(dest), file.filename, info["duration"])
        logger.info(
            "Uploaded video for project %s: %s (%.1fs)",
            project_id, file.filename, info["duration"],
        )
        
        # Auto-transcribe in background thread (non-blocking)
        orchestrator = ctx["orchestrator"]
        def transcribe_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(orchestrator.handle_prompt("transcribe this video"))
                loop.close()
                logger.info("Auto-transcription completed for project %s", project_id)
            except Exception as exc:
                logger.warning("Auto-transcription failed: %s", exc)
        
        transcribe_thread = threading.Thread(target=transcribe_async, daemon=True)
        transcribe_thread.start()
        logger.info("Started background transcription for project %s", project_id)
        
        return jsonify({
            "project_id": project_id,
            "source": str(dest),
            "duration": info["duration"],
            "width": info["width"],
            "height": info["height"],
            "auto_transcribed": True,
        })
    except Exception as exc:
        # ffprobe not available — still save the file
        state.set_source(str(dest), file.filename, 0.0)
        logger.warning("ffprobe failed: %s — saved file without duration info", exc)
        return jsonify({"project_id": project_id, "source": str(dest), "warning": str(exc)})


@app.route("/project/<project_id>/prompt", methods=["POST"])
def handle_prompt(project_id: str):
    """
    Send a natural-language prompt to the Orchestrator.
    Returns OrchestratorResult as JSON.
    """
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    orchestrator = ctx["orchestrator"]
    sse_q = ctx["sse_queue"]

    # Push start event to SSE
    sse_q.put_nowait(json.dumps({"event": "prompt_start", "data": {"prompt": prompt}}))

    # Run orchestrator in new event loop (Flask runs synchronously)
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(orchestrator.handle_prompt(prompt))
        loop.close()
    except Exception as exc:
        logger.exception("Orchestrator error: %s", exc)
        sse_q.put_nowait(json.dumps({"event": "error", "data": {"error": str(exc)}}))
        return jsonify({"error": str(exc)}), 500

    sse_q.put_nowait(json.dumps({
        "event": "prompt_done",
        "data": {
            "success": result.success,
            "summary": result.summary,
        },
    }))

    # Extract full_text from tool results if available (for search results)
    full_text = None
    for tc in result.tool_calls:
        if hasattr(tc, 'result') and tc.result and isinstance(tc.result.data, dict):
            if 'full_text' in tc.result.data:
                full_text = tc.result.data['full_text']
                break
    
    return jsonify({
        "success": result.success,
        "prompt": result.prompt,
        "summary": result.summary,
        "full_text": full_text,  # Include full text if available
        "tool_calls": [{"name": tc.name, "params": tc.params} for tc in result.tool_calls],
        "snap_id": result.snap_id,
        "error": result.error,
    })


@app.route("/project/<project_id>/timeline", methods=["GET"])
def get_timeline(project_id: str):
    """Return the current timeline state as JSON."""
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    state = ctx["state"]
    timeline_data = state.to_dict()

    # Build a GUI-friendly summary
    sequence = state.get_current_sequence()
    pool = state.get_all_segments()

    gui_segments = []
    for entry in sequence:
        seg = pool.get(entry.segment_id)
        if seg is None:
            continue
        search_layer = state.get_layer("search_agent", entry.segment_id)
        edit_layer = state.get_layer("edit_agent", entry.segment_id)
        gui_segments.append({
            "id": entry.segment_id,
            "start": seg.start,
            "end": seg.end,
            "duration": seg.duration,
            "text": seg.text,
            "speaker": seg.speaker,
            "transition_in": (
                {
                    "type": entry.transition_in.type.value,
                    "duration_s": entry.transition_in.duration_s,
                }
                if entry.transition_in else None
            ),
            "topics": search_layer.get("topics", []),
            "summary": search_layer.get("summary", ""),
            "effects": edit_layer.get("effects", []),
            "trim": edit_layer.get("trim", {}),
        })

    # Include full transcription for display (sorted by start time)
    transcription = []
    sorted_segments = sorted(pool.values(), key=lambda s: s.start)
    for seg in sorted_segments:
        transcription.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })
    
    return jsonify({
        "project_id": project_id,
        "source": state.get_source(),
        "segment_count": state.segment_count(),
        "current_sequence": gui_segments,
        "transcription": transcription,  # Full transcription with timestamps
        "history": state.get_history()[-10:],
        "snapshots": state.list_snapshots(),
    })


@app.route("/project/<project_id>/stream")
def sse_stream(project_id: str):
    """
    SSE endpoint — streams agent progress events to the browser.

    Format: text/event-stream with data: {event, data} JSON per event.
    """
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    sse_q = ctx["sse_queue"]

    def generate() -> Generator[str, None, None]:
        yield "data: {\"event\": \"connected\"}\n\n"
        while True:
            try:
                payload = sse_q.get(timeout=30)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                # Heartbeat to keep connection alive
                yield "data: {\"event\": \"heartbeat\"}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/project/<project_id>/rollback/<snap_id>", methods=["POST"])
def rollback(project_id: str, snap_id: str):
    """Rollback timeline to a specific snapshot."""
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    state = ctx["state"]
    success = state.rollback(snap_id)
    if not success:
        return jsonify({"error": f"Snapshot {snap_id} not found"}), 404

    return jsonify({"success": True, "snap_id": snap_id})


@app.route("/project/<project_id>/video")
def serve_source_video(project_id: str):
    """Serve the source video file."""
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    state = ctx["state"]
    source_path = state.source_path
    
    if not source_path or not Path(source_path).exists():
        return jsonify({"error": "Source video not found"}), 404

    return send_file(str(source_path), mimetype="video/mp4")


@app.route("/project/<project_id>/export/<filename>")
def serve_export(project_id: str, filename: str):
    """Serve an exported video file."""
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    state = ctx["state"]
    export_path = state.exports_dir / filename

    if not export_path.exists():
        return jsonify({"error": f"Export file not found: {filename}"}), 404

    return send_file(str(export_path), mimetype="video/mp4")


# ------------------------------------------------------------------
# Model warmup (pre-load models at startup)
# ------------------------------------------------------------------

def warmup_models():
    """Pre-load Whisper and sentence-transformers models to avoid first-use delay."""
    import os
    # Only warmup in main process, not in reloader subprocess
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        logger.info("Warming up models...")
        try:
            from agents.transcription_agent import _get_whisper, _select_model_size
            from pipeline.vectorizer import _get_model
            
            # Load Whisper model (uses auto-selected size based on RAM)
            model_size = _select_model_size("auto", CONFIG)
            _get_whisper(model_size)
            logger.info("✓ Whisper model pre-loaded")
            
            # Load sentence-transformers model
            _get_model()
            logger.info("✓ Sentence-transformers model pre-loaded")
            
            logger.info("Model warmup complete!")
        except Exception as e:
            logger.warning("Model warmup failed: %s (will lazy-load on first use)", e)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = True  # Always enable debug mode for auto-reload
    logger.info("Wizard starting on http://localhost:%d (debug=%s, auto-reload enabled)", port, debug)
    
    # Detect and log device configuration
    from utils.device import detect_device
    device_config = detect_device()
    logger.info("=" * 70)
    logger.info("DEVICE CONFIGURATION:")
    logger.info("  Device: %s", device_config.device_type.value.upper())
    if device_config.gpu_name:
        logger.info("  GPU: %s", device_config.gpu_name)
    if device_config.gpu_memory_gb:
        logger.info("  VRAM: %.1f GB", device_config.gpu_memory_gb)
    logger.info("  ONNX Providers:")
    for i, provider in enumerate(device_config.onnx_providers, 1):
        logger.info("    %d. %s", i, provider)
    logger.info("=" * 70)
    
    logger.info("Pre-loading models at startup...")
    
    # Warmup models before starting server
    warmup_models()
    
    logger.info("Auto-reload: File changes will restart the server automatically.")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=True, threaded=True)
