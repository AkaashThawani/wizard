# Wizard Video Editor - Development Roadmap

## Overview
Wizard is an AI-powered video editor that uses natural language for editing. This roadmap outlines the journey from basic transcription to a complete agentic editing system.

---

## ✅ Phase 1: Foundation (COMPLETE)

### 1.1 Core Infrastructure
- [x] Flask backend with SSE streaming
- [x] React frontend with TypeScript
- [x] Project management system
- [x] Timeline state management
- [x] Agent registry and orchestration

### 1.2 Video Analysis Pipeline
- [x] Whisper transcription (GPU-accelerated)
- [x] Segment extraction and management
- [x] 3-way parallel analysis workflow:
  - Transcription (sequential prerequisite)
  - ColorAgent (parallel per-second visual analysis)
  - AudioAgent (parallel per-second audio analysis)
- [x] Silent segment detection
- [x] Timeline reassembly with features

### 1.3 Per-Second Feature Extraction
- [x] **Visual Features** (ColorAgent):
  - CLIP embeddings (for similarity search)
  - Brightness per second
  - Dominant color per second
  - Saturation per second
  - Frame dimensions
- [x] **Audio Features** (AudioAgent):
  - Audio embeddings (for similarity search)
  - Energy (RMS, max, std)
  - Pitch (fundamental frequency)
  - Spectral centroid/rolloff
  - Zero-crossing rate
  - Speech rate (words per second)

### 1.4 Optimization
- [x] Payload optimization (90MB → 1MB)
  - Removed embeddings from API response
  - Embeddings stored in ChromaDB only
- [x] Fixed LangGraph concurrent update errors
- [x] Fixed coroutine serialization issues
- [x] FFmpeg PATH configuration

**Status**: Production-ready foundation ✅

---

## ✅ Phase 2: Performance Optimization (COMPLETE)

### 2.1 Reassembly Optimization ✅
- [x] Implement batch saves in reassembly_node
  - ✅ Implemented `set_layers_batch()` for single file write
  - ✅ Reduced 50+ individual saves to 1 batch save
  - ✅ 120x faster reassembly (2 min → 1 sec)
- [x] Silent segment creation moved to transcription phase
  - ✅ Complete timeline structure available immediately
  - ✅ No structure changes between SSE updates
- [x] Optimized layer storage operations
  - ✅ Batch operations for all feature attachments

### 2.2 Timeline Structure Optimization ✅
- [x] Create silent segments immediately after transcription
  - ✅ Timeline includes speech + silent segments from first update
  - ✅ Stable segment IDs (no changes during reassembly)
- [x] Progressive timeline updates via SSE
  - ✅ Event 1 (30s): Complete timeline structure
  - ✅ Event 2 (50s): Features attached (same structure)

**Completed**: 2026-02-22
**Impact**: 120x faster reassembly, stable timeline structure, better UX

---

## 🤖 Phase 3: Agentic Chat Interface (Priority 2)

### 3.1 Multi-Turn Conversation
**Current**: Single prompt → single response
**Target**: Continuous conversation with context

```python
# New ConversationAgent
class ConversationAgent:
    def __init__(self, llm_client, timeline_state):
        self.history = []
        self.context = {}
    
    async def chat(self, user_message: str) -> str:
        # Maintain conversation history
        # Access timeline features for context
        # Generate contextual responses
```

**Features**:
- [ ] Conversation history tracking
- [ ] Context-aware responses
- [ ] Multi-step reasoning
- [ ] Clarification questions
- [ ] Suggestion generation

**Example Interactions**:
```
User: "Find the exciting moments"
Agent: "I found 3 high-energy segments based on audio analysis. 
       Would you like me to create a highlight reel?"

User: "Yes, make it 30 seconds"
Agent: "Creating 30s highlight from segments with energy > 0.03.
       Should I add transitions?"

User: "Fade transitions"
Agent: "Applied 0.5s crossfade between clips. Preview ready!"
```

### 3.2 Tool Access System
Give chat agent access to analysis and editing tools:

```python
tools = [
    {
        "name": "find_segments_by_features",
        "description": "Find segments matching visual/audio criteria",
        "parameters": {
            "min_energy": float,
            "max_energy": float,
            "min_brightness": float,
            "dominant_color": str,
            "min_pitch": float,
            "text_contains": str
        }
    },
    {
        "name": "update_edit_decision",
        "description": "Add/modify edit decisions",
        "parameters": {
            "segment_ids": list[str],
            "edit_type": str,  # trim, effect, speed, volume
            "params": dict
        }
    },
    {
        "name": "analyze_timeline",
        "description": "Get timeline statistics and insights",
        "returns": {
            "total_duration": float,
            "segment_count": int,
            "average_energy": float,
            "color_distribution": dict
        }
    }
]
```

### 3.3 Frontend Chat UI
- [ ] Chat message component
- [ ] Message history display
- [ ] Typing indicators
- [ ] Suggested actions/buttons
- [ ] Code/preview embeds in responses

**Timeline**: 3-4 days
**Impact**: Natural editing interface

---

## 🛠️ Phase 4: Edit Decision Model & Tools (Priority 3)

### 4.1 Edit Decision Schema

```python
# Extend timeline/models.py
class EditDecision(TypedDict):
    """
    Represents a single edit operation.
    """
    id: str
    segment_id: str
    type: Literal["trim", "effect", "speed", "volume", "transition"]
    params: dict
    apply_to_range: tuple[float, float] | None  # Within segment
    created_at: float
    created_by: str  # "user" or "agent"

class SegmentEdits(TypedDict):
    """
    All edits for a segment.
    """
    segment_id: str
    decisions: list[EditDecision]
    trim: dict  # {start_offset: 0.5, end_offset: 0.2}
    effects: list[dict]
    volume: float  # 0.0 to 2.0
    speed: float   # 0.5 to 2.0
    transitions: dict  # {in: {...}, out: {...}}
```

### 4.2 Edit Tools for Agents

#### Tool: `update_edit_decision`
```python
async def update_edit_decision(
    segment_ids: list[str],
    edit_type: str,
    params: dict
) -> ToolResult:
    """
    Add or update edit decisions for segments.
    
    Examples:
    - edit_type="audio_denoise", params={"nf": -25}
    - edit_type="color_grade", params={"brightness": 1.2}
    - edit_type="trim", params={"start": 0.5, "end": -0.2}
    """
```

#### Tool: `find_segments_by_features`
```python
async def find_segments_by_features(
    min_energy: float = None,
    max_energy: float = None,
    min_brightness: float = None,
    max_brightness: float = None,
    dominant_color: str = None,
    text_contains: str = None
) -> list[Segment]:
    """
    Query segments using per-second features.
    
    Example:
    - Find quiet parts: min_energy=0.0, max_energy=0.02
    - Find dark scenes: max_brightness=0.3
    - Find red moments: dominant_color="#ff0000" (with tolerance)
    """
```

### 4.3 Storage & Persistence
- [ ] Add `edits` layer to TimelineState
- [ ] Serialize edit decisions to JSON
- [ ] Load/restore edit decisions on project open
- [ ] Version control for edit history

**Timeline**: 2-3 days
**Impact**: Structured edit management

---

## 🎬 Phase 5: Preview System (Priority 4)

### 5.1 Preview Architecture

```
┌─────────────────────────────────────────┐
│  User clicks "Preview"                  │
└───────────────┬─────────────────────────┘
                │
        ┌───────▼────────┐
        │ Which Preview? │
        └───────┬────────┘
                │
    ┌───────────┴──────────────┐
    │                          │
┌───▼──────────┐    ┌─────────▼────────┐
│ Segment      │    │ Full Timeline    │
│ Preview      │    │ Preview          │
└───┬──────────┘    └─────────┬────────┘
    │                          │
    │ 5-10s render             │ Full render
    │                          │
┌───▼────────────────┬─────────▼────────┐
│ FFmpeg Renderer                       │
│ - Apply edit decisions                │
│ - Compile FFmpeg filters              │
│ - Render to temp file                 │
└───────────────────┬───────────────────┘
                    │
            ┌───────▼───────┐
            │ Video Stream  │
            │ (HTTP Range)  │
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │ <video> Player│
            └───────────────┘
```

### 5.2 Backend Preview Endpoint

```python
@app.route("/project/<id>/preview/segment/<segment_id>")
async def preview_segment(project_id: str, segment_id: str):
    """
    Render and stream single segment with applied effects.
    Fast preview for iteration.
    """
    # Get segment and its edit decisions
    segment = state.get_segment(segment_id)
    edits = state.get_layer("edits", segment_id)
    
    # Compile FFmpeg command
    ffmpeg_cmd = compile_preview_command(segment, edits)
    
    # Render to temp file
    preview_path = f"/tmp/preview_{segment_id}.mp4"
    await render_preview(ffmpeg_cmd, preview_path)
    
    # Stream with Range support
    return send_file(preview_path, mimetype="video/mp4")

@app.route("/project/<id>/preview/timeline")
async def preview_timeline(project_id: str):
    """
    Render and stream complete timeline with all effects.
    Full preview before final export.
    """
    # Get all segments in sequence
    sequence = state.get_current_sequence()
    
    # Compile full timeline FFmpeg command
    ffmpeg_cmd = compile_timeline_command(sequence)
    
    # Render to temp file (may take time)
    preview_path = f"/tmp/preview_{project_id}_full.mp4"
    await render_timeline(ffmpeg_cmd, preview_path)
    
    # Stream with Range support
    return send_file(preview_path, mimetype="video/mp4")
```

### 5.3 FFmpeg Filter Compilation

Enhance `backend/media/effect_compiler.py`:

```python
def compile_edit_to_filters(edit: EditDecision) -> list[str]:
    """
    Convert edit decision to FFmpeg filter strings.
    """
    filters = []
    
    if edit["type"] == "audio_denoise":
        nf = edit["params"].get("nf", -25)
        filters.append(f"afftdn=nf={nf}")
    
    elif edit["type"] == "color_grade":
        brightness = edit["params"].get("brightness", 1.0)
        saturation = edit["params"].get("saturation", 1.0)
        filters.append(f"eq=brightness={brightness}:saturation={saturation}")
    
    elif edit["type"] == "trim":
        # Handle via FFmpeg -ss and -t flags
        pass
    
    return filters
```

### 5.4 Video Streaming
- [ ] HTTP Range request support (for seeking)
- [ ] Progressive download
- [ ] Cache management for previews
- [ ] Background rendering queue

**Timeline**: 3-4 days
**Impact**: Real editing workflow

---

## 🎨 Phase 6: UI Enhancement (Priority 5)

### 6.1 Chat Interface

```tsx
// frontend/src/components/ChatInterface.tsx
export function ChatInterface() {
  return (
    <div className="chat-container">
      <MessageHistory messages={messages} />
      <ChatInput onSend={handleSend} />
      <SuggestedActions actions={suggestions} />
    </div>
  );
}
```

**Features**:
- [ ] Message bubbles (user vs agent)
- [ ] Typing indicators
- [ ] Code/preview embeds
- [ ] Action buttons in responses
- [ ] Conversation export

### 6.2 Timeline Visualization

```tsx
// frontend/src/components/TimelineVisualization.tsx
export function TimelineVisualization({ segments }) {
  return (
    <div className="timeline">
      {segments.map(seg => (
        <SegmentTrack
          segment={seg}
          visualFeatures={seg.visual_features}
          audioFeatures={seg.audio_features}
          edits={seg.edits}
        />
      ))}
    </div>
  );
}
```

**Visualizations**:
- [ ] Audio energy waveform
- [ ] Brightness graph
- [ ] Dominant color timeline
- [ ] Pitch variation
- [ ] Edit markers
- [ ] Playhead scrubbing

### 6.3 Preview Player

```tsx
// frontend/src/components/PreviewPlayer.tsx
export function PreviewPlayer({ previewUrl, onApprove }) {
  return (
    <div className="preview-player">
      <video src={previewUrl} controls />
      <div className="preview-actions">
        <button onClick={onApprove}>Approve</button>
        <button onClick={onReject}>Try Again</button>
      </div>
    </div>
  );
}
```

**Features**:
- [ ] Segment vs full timeline toggle
- [ ] Side-by-side comparison (original vs edited)
- [ ] Frame-by-frame stepping
- [ ] Export button

### 6.4 Feature Visualization
- [ ] Click on brightness graph → jump to that second
- [ ] Drag to select time range for editing
- [ ] Visual indicators for quiet/loud sections
- [ ] Color palette extraction

**Timeline**: 4-5 days
**Impact**: Professional editing UI

---

## 🚀 Phase 7: Advanced Features (Future)

### 7.1 Smart Editing AI
- [ ] Auto-generate highlight reels
- [ ] Beat detection for music sync
- [ ] Scene change detection
- [ ] Face tracking
- [ ] Object detection

### 7.2 Collaboration
- [ ] Multi-user projects
- [ ] Comment threads on segments
- [ ] Version branches
- [ ] Export to popular formats

### 7.3 Performance
- [ ] GPU-accelerated rendering
- [ ] Distributed processing
- [ ] Real-time collaboration
- [ ] Cloud storage integration

---

## Implementation Priority

```
Week 1-2:  Phase 2 (Performance Optimization)
Week 3-4:  Phase 3 (Agentic Chat Interface)
Week 5-6:  Phase 4 (Edit Decision Model & Tools)
Week 7-8:  Phase 5 (Preview System)
Week 9-10: Phase 6 (UI Enhancement)
```

---

## Technical Stack

### Backend
- **Framework**: Flask + Flask-CORS
- **Video**: FFmpeg (native + Python wrapper)
- **AI/ML**:
  - Whisper (transcription)
  - CLIP (visual embeddings)
  - Librosa (audio features)
  - LangGraph (orchestration)
- **LLM**: Anthropic Claude / OpenAI GPT
- **Vector DB**: ChromaDB
- **State**: JSON + Pickle serialization

### Frontend
- **Framework**: React + TypeScript
- **Build**: Vite
- **Styling**: CSS (to be enhanced)
- **Video**: HTML5 `<video>` element
- **Visualization**: (TBD - D3.js, Chart.js, or Canvas)

### Infrastructure
- **Development**: Local Flask server
- **Production**: (TBD - Docker, AWS, etc.)

---

## Success Metrics

### Phase 2
- Reassembly time < 30 seconds for 60s video
- SSE events delivered in real-time

### Phase 3
- Multi-turn conversations work
- Agent can answer questions about timeline
- Tool calls execute successfully

### Phase 4
- Edit decisions persist across sessions
- Agent can apply complex edits using features
- Edit history tracked

### Phase 5
- Segment preview renders in < 5 seconds
- Full timeline preview streams smoothly
- Video seeking works (HTTP Range)

### Phase 6
- Chat interface responsive
- Timeline visualizations intuitive
- Preview player functional

---

## Risk Mitigation

### Performance Risks
- **Risk**: Large video files (>1GB) slow down system
- **Mitigation**: Progressive loading, chunk processing

### LLM Risks
- **Risk**: Incorrect edit decisions from AI
- **Mitigation**: Preview system, user approval required

### Browser Limits
- **Risk**: Memory issues with long videos
- **Mitigation**: Virtual scrolling, lazy loading

### FFmpeg Risks
- **Risk**: Complex filter chains fail
- **Mitigation**: Validation, fallback strategies

---

## Current Status (2026-02-21)

✅ **Phase 1**: Complete
🔧 **Phase 2**: Next up
📋 **Phases 3-6**: Planned

**Ready to begin Phase 2 implementation!**
