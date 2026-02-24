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
import warnings
from pathlib import Path
from typing import Generator, Any

from dotenv import load_dotenv
load_dotenv()  # loads .env from project root before anything else

from flask import Flask, Response, jsonify, request, send_file, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room

from timeline.state import TimelineState
from agents.registry import AgentRegistry
from agents.transcription_agent import TranscriptionAgent
from agents.search_agent import SearchAgent
from agents.edit_agent import EditAgent
from agents.export_agent import ExportAgent
from agents.color_agent import ColorAgent
from agents.audio_agent import AudioAgent
from llm.client import LLMClient
from orchestrator.auto_analysis import create_agent_graph
from orchestrator.chat_workflow import create_chat_workflow  # NEW: ReAct agent
from orchestrator.sse_manager import SSEConnectionManager

# Suppress warnings from transformers and other libraries
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore")
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_LOG_LEVEL"] = "ERROR"
os.environ["CHROMA_TELEMETRY"] = "False"

logging.basicConfig(
    level=logging.WARNING,  # Only show WARNING and ERROR (suppress INFO)
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# But keep our app's logger at INFO level for important messages
logger.setLevel(logging.INFO)

# Enable LLM client logging to see tool calls
logging.getLogger("llm.client").setLevel(logging.INFO)
logging.getLogger("orchestrator.llm_orchestrator_node").setLevel(logging.INFO)

# Enable LangGraph/LangChain logging to see agent reasoning (DEBUG for full details)
logging.getLogger("langgraph").setLevel(logging.DEBUG)
logging.getLogger("langchain").setLevel(logging.DEBUG)
logging.getLogger("langchain_core").setLevel(logging.DEBUG)
logging.getLogger("langchain_core.runnables").setLevel(logging.DEBUG)
logging.getLogger("orchestrator.chat_workflow").setLevel(logging.DEBUG)

# Enable Gemini-specific loggers
logging.getLogger("langchain_google_genai").setLevel(logging.DEBUG)
logging.getLogger("google.generativeai").setLevel(logging.INFO)
logging.getLogger("google.ai.generativelanguage").setLevel(logging.INFO)

# Enable export and FFmpeg logging to see export process
logging.getLogger("agents.export_agent").setLevel(logging.INFO)
logging.getLogger("media.ffmpeg_wrapper").setLevel(logging.INFO)
logging.getLogger("media.effect_compiler").setLevel(logging.INFO)

# Silence ALL noisy libraries completely
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("huggingface_hub").setLevel(logging.CRITICAL)
logging.getLogger("transformers").setLevel(logging.CRITICAL)
logging.getLogger("sentence_transformers").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("filelock").setLevel(logging.CRITICAL)
logging.getLogger("chromadb").setLevel(logging.CRITICAL)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

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

# Initialize SocketIO with CORS support
socketio = SocketIO(
    app,
    cors_allowed_origins=["http://localhost:5173"],
    async_mode='threading',
    logger=False,
    engineio_logger=False
)


# ------------------------------------------------------------------
# Helper: get or create project context
# ------------------------------------------------------------------

def _get_project(project_id: str) -> dict | None:
    return _projects.get(project_id)


def _register_agents_from_config(
    state: Any,
    config: dict,
    llm_client: Any,
    progress_callback: Any
) -> Any:
    """
    Dynamically register agents based on config.json settings.
    
    Only registers agents where config["agents"][agent_name]["enabled"] == True
    
    Args:
        state: TimelineState instance
        config: Loaded config.json
        llm_client: LLM client for agents that need it
        progress_callback: SSE callback
    
    Returns:
        AgentRegistry with enabled agents registered
    """
    from agents.registry import AgentRegistry
    from agents.transcription_agent import TranscriptionAgent
    from agents.search_agent import SearchAgent
    from agents.edit_agent import EditAgent
    from agents.export_agent import ExportAgent
    from agents.color_agent import ColorAgent
    from agents.audio_agent import AudioAgent
    from agents.conversation_agent import ConversationAgent
    from agents.timeline_agent import TimelineAgent
    
    registry = AgentRegistry()
    agent_config = {"whisper_model": config.get("whisper", {}).get("model_size", "base"), **config}
    
    # Conditional registration based on config
    if config.get("agents", {}).get("transcription", {}).get("enabled", True):
        registry.register(TranscriptionAgent(state, agent_config, progress_callback))
        logger.info("✓ Registered TranscriptionAgent")
    
    if config.get("agents", {}).get("search", {}).get("enabled", True):
        registry.register(SearchAgent(state, agent_config, llm_client, progress_callback))
        logger.info("✓ Registered SearchAgent")
    
    if config.get("agents", {}).get("edit", {}).get("enabled", True):
        registry.register(EditAgent(state, agent_config, progress_callback))
        logger.info("✓ Registered EditAgent")
    
    if config.get("agents", {}).get("export", {}).get("enabled", True):
        registry.register(ExportAgent(state, agent_config, progress_callback))
        logger.info("✓ Registered ExportAgent")
    
    if config.get("agents", {}).get("color", {}).get("enabled", True):
        registry.register(ColorAgent(state, agent_config, progress_callback))
        logger.info("✓ Registered ColorAgent")
    
    if config.get("agents", {}).get("audio", {}).get("enabled", True):
        registry.register(AudioAgent(state, agent_config, progress_callback))
        logger.info("✓ Registered AudioAgent")
    
    # Always register ConversationAgent (handles casual chat)
    registry.register(ConversationAgent(state, agent_config, progress_callback))
    logger.info("✓ Registered ConversationAgent")
    
    # Always register TimelineAgent (query timeline state)
    registry.register(TimelineAgent(state, agent_config, progress_callback))
    logger.info("✓ Registered TimelineAgent")
    
    return registry


def _create_project_context(project_id: str) -> dict:
    """Create project context with auto-analysis and chat workflows."""
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

    # Use dynamic agent registration from config
    registry = _register_agents_from_config(state, CONFIG, llm_client, progress_callback)

    # Create SSE manager for 2-phase workflow
    sse_manager = SSEConnectionManager()
    
    # Create auto-analysis workflow (for upload)
    auto_workflow = create_agent_graph(registry, state, CONFIG, sse_manager)
    
    # Create chat workflow using ReAct agent (for manual prompts)
    chat_workflow = create_chat_workflow(registry, state, llm_client, CONFIG)

    ctx = {
        "state": state,
        "auto_workflow": auto_workflow,
        "chat_workflow": chat_workflow,  # Changed from prompt_workflow
        "sse_manager": sse_manager,
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
        
        # Auto-transcribe and analyze using 2-phase workflow (non-blocking)
        auto_workflow = ctx["auto_workflow"]
        sse_manager = ctx["sse_manager"]
        sse_q = ctx["sse_queue"]
        
        def transcribe_and_analyze_async():
            """
            2-phase workflow: Transcription → Analysis
            
            Phase 1: Transcription (sequential - must complete first)
            Phase 2: Color + Audio analysis (parallel - need segments from phase 1)
            
            Fixes the parallel execution bug where color/audio ran before segments existed.
            """
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                logger.info("🚀 Starting 2-phase auto-analysis for project %s", project_id)
                
                # Execute 2-phase auto-analysis workflow
                result = loop.run_until_complete(auto_workflow.invoke({
                    "project_id": project_id,
                    "prompt": "auto-analysis"
                }))
                
                # Send SSE events from sse_manager to sse_queue
                # (sse_manager stores events, we need to push them to Flask SSE)
                for event_dict in sse_manager.get_events_since(project_id, None):
                    sse_q.put_nowait(json.dumps(event_dict))
                
                # Send final completion event
                if result.get("success"):
                    logger.info("✓ 2-phase workflow complete for project %s", project_id)
                    event_data = {
                        "event": "prompt_done",
                        "data": {
                            "success": True,
                            "summary": result.get("summary", "Auto-analysis complete"),
                            "transcription_done": result.get("transcription_done", False),
                            "color_done": result.get("color_done", False),
                            "audio_done": result.get("audio_done", False),
                            "segments_count": result.get("segments_count", 0),
                        }
                    }
                else:
                    logger.error("✗ 2-phase workflow failed for project %s: %s", 
                               project_id, result.get("error"))
                    event_data = {
                        "event": "error",
                        "data": {
                            "error": result.get("error", "Unknown error"),
                            "message": "Auto-analysis failed"
                        }
                    }
                
                sse_q.put_nowait(json.dumps(event_data))
                logger.info("📤 Sent final event to SSE queue")
                
                loop.close()
            except Exception as exc:
                logger.exception("Auto-transcription/analysis failed: %s", exc)
                sse_q.put_nowait(json.dumps({
                    "event": "error",
                    "data": {"error": str(exc), "message": "Workflow execution failed"}
                }))
        
        transcribe_thread = threading.Thread(target=transcribe_and_analyze_async, daemon=True)
        transcribe_thread.start()
        logger.info("Started background 2-phase workflow for project %s", project_id)
        
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

    chat_workflow = ctx["chat_workflow"]
    sse_q = ctx["sse_queue"]

    # Push start event to SSE
    sse_q.put_nowait(json.dumps({"event": "prompt_start", "data": {"prompt": prompt}}))

    # Run chat workflow in new event loop (Flask runs synchronously)
    try:
        from orchestrator.chat_workflow import invoke_chat_workflow
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(invoke_chat_workflow(
            agent=chat_workflow,
            project_id=project_id,
            prompt=prompt,
            timeline_state=ctx["state"]
        ))
        loop.close()
    except Exception as exc:
        logger.exception("Prompt workflow error: %s", exc)
        sse_q.put_nowait(json.dumps({"event": "error", "data": {"error": str(exc)}}))
        return jsonify({"error": str(exc)}), 500

    # Send done event
    sse_q.put_nowait(json.dumps({
        "event": "prompt_done",
        "data": {
            "success": result.get("success", False),
            "summary": result.get("summary", ""),
        },
    }))
    
    # Extract results for response
    results_data = result.get("results", [])
    
    return jsonify({
        "success": result.get("success", False),
        "prompt": prompt,
        "summary": result.get("summary", ""),
        "results": results_data,
        "error": result.get("error"),
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
        color_layer = state.get_layer("color_agent", entry.segment_id)
        audio_layer = state.get_layer("audio_agent", entry.segment_id)
        
        # Visual features are now per-second arrays from ColorAgent
        # Remove clip_embedding to reduce payload (not needed in frontend - only for ChromaDB)
        visual_features = None
        if color_layer:
            visual_features = [
                {k: v for k, v in feat.items() if k != "clip_embedding"}
                for feat in color_layer
            ]
        
        # Audio features are now per-second arrays from AudioAgent
        # Remove audio_embedding to reduce payload (not needed in frontend - only for ChromaDB)
        audio_features = None
        if audio_layer:
            audio_features = [
                {k: v for k, v in feat.items() if k != "audio_embedding"}
                for feat in audio_layer
            ]
        
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
            "visual_features": visual_features,
            "audio_features": audio_features,
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
    
    # Build edit decision model (EDL) - shows all edit layers
    edit_decisions = {}
    edit_layers = state.get_agent_layer("edit_agent")
    for seg_id, edit_data in edit_layers.items():
        edit_decisions[seg_id] = {
            "trim": edit_data.get("trim", {}),
            "effects": edit_data.get("effects", []),
        }
    
    # Build effective (virtual) timeline showing segments with edits applied
    effective_timeline = []
    for entry in sequence:
        effective_seg = state.get_effective_segment(entry.segment_id)
        if effective_seg:
            effective_timeline.append({
                "id": effective_seg.id,
                "start": round(effective_seg.start, 2),
                "end": round(effective_seg.end, 2),
                "duration": round(effective_seg.duration, 2),
                "text": effective_seg.text[:100],
            })
    
    return jsonify({
        "project_id": project_id,
        "source": state.get_source(),
        "segment_count": state.segment_count(),
        "current_sequence": gui_segments,
        "transcription": transcription,  # Full transcription with timestamps
        "edit_decisions": edit_decisions,  # Edit Decision Model (EDL)
        "effective_timeline": effective_timeline,  # Virtual timeline with edits applied
        "history": state.get_history()[-10:],
        "snapshots": state.list_snapshots(),
    })


@app.route("/project/<project_id>/stream")
def sse_stream(project_id: str):
    """
    SSE endpoint — streams agent progress events to the browser.
    
    Supports reconnection with checkpoint parameter:
      /project/{id}/stream?since={checkpoint_id}
    
    When 'since' is provided, sends all events after that checkpoint.

    Format: text/event-stream with data: {event, data} JSON per event.
    """
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    sse_q = ctx["sse_queue"]
    sse_manager = ctx["sse_manager"]
    
    # Check for checkpoint parameter (for reconnection)
    since_checkpoint = request.args.get("since")

    def generate() -> Generator[str, None, None]:
        # Send connection confirmation
        yield "data: {\"event\": \"connected\"}\n\n"
        
        # If reconnecting, replay events since checkpoint
        if since_checkpoint:
            logger.info("SSE reconnection for project %s from checkpoint %s", project_id, since_checkpoint)
            try:
                # Get missed events from SSE manager
                missed_events = sse_manager.get_events_since(project_id, since_checkpoint)
                for event_dict in missed_events:
                    payload = json.dumps(event_dict)
                    yield f"data: {payload}\n\n"
                logger.info("Replayed %d missed events", len(missed_events))
            except Exception as exc:
                logger.warning("Failed to replay events: %s", exc)
        
        # Stream new events
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


@app.route("/project/<project_id>/chat/history", methods=["GET"])
def get_chat_history(project_id: str):
    """
    Get conversation history for a project from SqliteSaver.
    
    Returns all chat messages stored in checkpoints.db for this project.
    Useful for restoring conversation on page reload or reconnection.
    """
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404
    
    try:
        # Access SqliteSaver checkpoints
        chat_workflow = ctx["chat_workflow"]
        
        # Get conversation history from checkpoints
        # LangGraph stores state in checkpoints, we need to extract messages
        # For now, return from timeline.history which we'll populate with chat summaries
        state = ctx["state"]
        history = state.get_history()
        
        # Filter to only chat-related entries
        chat_history = [
            {
                "prompt": h.get("prompt", ""),
                "summary": h.get("summary", ""),
                "timestamp": h.get("timestamp"),
                "success": h.get("success", True)
            }
            for h in history
            if h.get("prompt")  # Only include entries with prompts (chat messages)
        ]
        
        return jsonify({
            "project_id": project_id,
            "messages": chat_history,
            "count": len(chat_history)
        })
        
    except Exception as exc:
        logger.exception("Failed to get chat history: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/project/<project_id>/chat/export", methods=["GET"])
def export_chat_history(project_id: str):
    """
    Export conversation history as JSON file for download.
    
    Includes full chat history with timestamps, messages, and results.
    """
    ctx = _get_project(project_id)
    if ctx is None:
        return jsonify({"error": f"Project {project_id} not found"}), 404
    
    try:
        state = ctx["state"]
        history = state.get_history()
        
        # Build export data
        export_data = {
            "project_id": project_id,
            "export_timestamp": json.dumps({"timestamp": None}),  # Will be set by client
            "conversation": history,
            "total_messages": len(history)
        }
        
        # Return as downloadable JSON
        response = jsonify(export_data)
        response.headers["Content-Disposition"] = f"attachment; filename=chat_history_{project_id}.json"
        return response
        
    except Exception as exc:
        logger.exception("Failed to export chat history: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ------------------------------------------------------------------
# WebSocket handlers for agentic chat
# ------------------------------------------------------------------

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info("WebSocket client connected: %s", request.sid)
    emit('connected', {'message': 'Connected to Wizard chat server'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info("WebSocket client disconnected: %s", request.sid)


@socketio.on('join_project')
def handle_join_project(data):
    """
    Join a project room for chat.
    
    Message format:
    {
        "project_id": "abc123"
    }
    """
    project_id = data.get('project_id')
    
    if not project_id:
        emit('error', {'error': 'project_id required'})
        return
    
    # Verify project exists or create it
    ctx = _get_project(project_id)
    if ctx is None:
        ctx = _create_project_context(project_id)
    
    # Join Socket.IO room
    join_room(project_id)
    logger.info("Client %s joined project %s", request.sid, project_id)
    
    emit('joined_project', {
        'project_id': project_id,
        'message': f'Joined project {project_id}'
    })


@socketio.on('leave_project')
def handle_leave_project(data):
    """Leave a project room."""
    project_id = data.get('project_id')
    
    if not project_id:
        emit('error', {'error': 'project_id required'})
        return
    
    leave_room(project_id)
    logger.info("Client %s left project %s", request.sid, project_id)
    
    emit('left_project', {'project_id': project_id})


@socketio.on('chat_message')
def handle_chat_message(data):
    """
    Handle chat message from client.
    
    Message format:
    {
        "project_id": "abc123",
        "message": "trim the first segment",
        "timestamp": 1234567890
    }
    
    Executes the prompt workflow and streams results via Socket.IO.
    """
    project_id = data.get('project_id')
    message = data.get('message', '').strip()
    timestamp = data.get('timestamp')
    
    if not project_id or not message:
        emit('error', {'error': 'project_id and message required'})
        return
    
    ctx = _get_project(project_id)
    if ctx is None:
        emit('error', {'error': f'Project {project_id} not found'})
        return
    
    logger.info("Chat message from %s in project %s: %s", request.sid, project_id, message)
    
    # Echo message back to room (confirmation)
    socketio.emit('chat_message', {
        'role': 'user',
        'content': message,
        'timestamp': timestamp,
        'project_id': project_id
    }, room=project_id)
    
    # Send "assistant is thinking" indicator
    socketio.emit('chat_status', {
        'status': 'thinking',
        'project_id': project_id
    }, room=project_id)
    
    # Execute chat workflow in background thread
    def execute_chat_prompt():
        """Execute chat workflow and send results via WebSocket."""
        try:
            from orchestrator.chat_workflow import invoke_chat_workflow
            
            chat_workflow = ctx["chat_workflow"]
            sse_q = ctx["sse_queue"]
            
            # Run workflow
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(invoke_chat_workflow(
                agent=chat_workflow,
                project_id=project_id,
                prompt=message,
                timeline_state=ctx["state"]
            ))
            
            loop.close()
            
            # Send assistant response
            if result.get("success"):
                results = result.get("results", [])
                
                # Extract conversation.talk_user message from results
                # Now we look in the 'result' field, not 'params'
                conversation_message = None
                for tool_result in results:
                    if tool_result.get("tool") == "conversation.talk_user":
                        # Check result field first (this is the actual tool output)
                        result_data = tool_result.get("result", {})
                        if isinstance(result_data, dict):
                            conversation_message = result_data.get("message", "")
                        # Fallback to params if result not found (backwards compatibility)
                        if not conversation_message:
                            conversation_message = tool_result.get("params", {}).get("message", "")
                        if conversation_message:
                            break
                
                # Use conversation message if available, otherwise fallback to summary
                response_message = conversation_message or result.get("summary", "Done!")
                
                # Emit tool progress events to SSE for UI feedback
                for tool_result in results:
                    tool_name = tool_result.get("tool", "")
                    
                    # Friendly tool names for display
                    tool_display = {
                        "search.find_segments": "Searching clips",
                        "edit.keep_only": "Filtering segments",
                        "edit.remove_short": "Removing short clips",
                        "edit.trim_segment": "Trimming",
                        "edit.split_segment": "Splitting",
                        "export.export": "Exporting video",
                    }.get(tool_name, tool_name)
                    
                    # Emit SSE progress event
                    sse_q.put_nowait(json.dumps({
                        "event": "stage",
                        "data": {"stage": tool_display, "status": "done"}
                    }))
                    
                    # If export tool completed, emit encode done event to trigger download
                    if tool_name == "export.export" and tool_result.get("success"):
                        sse_q.put_nowait(json.dumps({
                            "event": "stage",
                            "data": {"stage": "encode", "status": "done"}
                        }))
                        logger.info("Emitted SSE encode done event for auto-download")
                
                # Save to timeline history for persistence
                state = ctx["state"]
                state.add_history(message, response_message)
                state.save()
                
                socketio.emit('chat_message', {
                    'role': 'assistant',
                    'content': response_message,
                    'timestamp': None,  # Server generates timestamp
                    'project_id': project_id,
                    'results': results
                }, room=project_id)
                
                logger.info("Chat response sent for project %s", project_id)
            else:
                # Send error message
                error_message = result.get("error", "Something went wrong")
                
                socketio.emit('chat_message', {
                    'role': 'assistant',
                    'content': f"Error: {error_message}",
                    'timestamp': None,
                    'project_id': project_id,
                    'error': True
                }, room=project_id)
                
                logger.error("Chat prompt failed for project %s: %s", project_id, error_message)
            
            # Clear thinking status
            socketio.emit('chat_status', {
                'status': 'idle',
                'project_id': project_id
            }, room=project_id)
            
        except Exception as exc:
            logger.exception("Chat prompt execution error: %s", exc)
            
            # Send error to client
            socketio.emit('chat_message', {
                'role': 'assistant',
                'content': f"Error: {str(exc)}",
                'timestamp': None,
                'project_id': project_id,
                'error': True
            }, room=project_id)
            
            socketio.emit('chat_status', {
                'status': 'idle',
                'project_id': project_id
            }, room=project_id)
    
    # Start background thread
    chat_thread = threading.Thread(target=execute_chat_prompt, daemon=True)
    chat_thread.start()


# ------------------------------------------------------------------
# Model warmup (pre-load models at startup)
# ------------------------------------------------------------------

def warmup_models():
    """Pre-load models in parallel at startup for faster initialization."""
    import os
    import concurrent.futures
    import time
    
    # Only warmup in main process, not in reloader subprocess
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        logger.info("Warming up models in parallel...")
        start_time = time.time()
        
        try:
            from agents.transcription_agent import _get_whisper, _select_model_size
            from pipeline.vectorizer import _get_model
            from agents.color_agent import _get_clip_model
            from utils.device import detect_device
            
            device_config = detect_device()
            model_size = _select_model_size("auto", CONFIG)
            
            # Define loader functions
            def load_whisper():
                logger.info("Loading Whisper model (%s)...", model_size)
                _get_whisper(model_size)
                logger.info("✓ Whisper model pre-loaded")
                return "whisper"
            
            def load_embeddings():
                logger.info("Loading sentence-transformers model...")
                _get_model()
                logger.info("✓ Sentence-transformers model pre-loaded")
                return "embeddings"
            
            def load_clip():
                logger.info("Loading CLIP model...")
                _get_clip_model(device_config)
                logger.info("✓ CLIP model pre-loaded (on %s)", device_config.device_type.value.upper())
                return "clip"
            
            # Load all models in parallel using ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all loads simultaneously
                futures = {
                    executor.submit(load_whisper): "Whisper",
                    executor.submit(load_embeddings): "Embeddings",
                    executor.submit(load_clip): "CLIP"
                }
                
                # Wait for all to complete
                for future in concurrent.futures.as_completed(futures):
                    model_name = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logger.error("%s model loading failed: %s", model_name, exc)
            
            elapsed = time.time() - start_time
            logger.info("=" * 70)
            logger.info("🎉 Model warmup complete! All models ready in %.1fs", elapsed)
            logger.info("=" * 70)
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
    logger.info("WebSocket chat endpoint: ws://localhost:%d", port)
    
    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, use_reloader=True, allow_unsafe_werkzeug=True)
