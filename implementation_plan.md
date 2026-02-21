# Implementation Plan: CUDA Support, Agent Configuration, and ONNX Runtime Integration

[Overview]
Implement device detection with CUDA/Apple Silicon support, add agent toggle flags to config, migrate to ONNX Runtime for ML models, and ensure proper agent integration with orchestrator and state management.

This implementation addresses four critical gaps in the current system:

1. **Device Detection**: The system currently uses PyTorch without explicit device configuration, leading to inefficient CPU-only execution even when CUDA or Apple Silicon accelerators are available. We need automatic hardware detection with graceful fallbacks.

2. **Agent Configuration**: There's no way to enable/disable individual agents or control auto-analysis behavior. This makes it impossible to run the system in different modes (e.g., transcription-only, full analysis pipeline, etc.).

3. **ONNX Runtime Migration**: Despite having `optimum[onnxruntime]` installed, the codebase uses PyTorch directly via `transformers.pipeline()`. This misses 2-3x performance improvements and proper GPU utilization that ONNX Runtime provides.

4. **Agent Integration**: ColorAgent and AudioAgent are stubbed and not integrated into the analysis pipeline, meaning visual and audio semantic search capabilities are unavailable.

The solution involves creating a centralized device detection module, extending the config schema, migrating model loading to ONNX Runtime, un-stubbing ColorAgent and AudioAgent with proper implementations, and updating the orchestrator to respect agent configuration flags.

[Types]
Define device configuration types, agent configuration schemas, and ONNX provider specifications.

**New Type Definitions:**

```python
# backend/utils/device.py
from enum import Enum
from dataclasses import dataclass

class DeviceType(str, Enum):
    """Available device types for model inference."""
    CUDA = "cuda"
    APPLE_SILICON = "mps"  # Metal Performance Shaders
    CPU = "cpu"

class ONNXProvider(str, Enum):
    """ONNX Runtime execution providers."""
    CUDA = "CUDAExecutionProvider"
    TENSORRT = "TensorrtExecutionProvider"
    COREML = "CoreMLExecutionProvider"
    DIRECTML = "DmlExecutionProvider"  # Windows DirectX
    CPU = "CPUExecutionProvider"

@dataclass
class DeviceConfig:
    """Device detection and configuration result."""
    device_type: DeviceType
    onnx_providers: list[str]
    cuda_available: bool
    mps_available: bool
    gpu_name: str | None
    gpu_memory_gb: float | None
```

**Config Schema Extensions:**

```json
{
  "device": {
    "cuda_enabled": true,
    "auto_detect": true,
    "preferred_providers": ["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]
  },
  "agents": {
    "transcription": {
      "enabled": true,
      "auto_run": true
    },
    "color": {
      "enabled": true,
      "auto_analyze": false,
      "model": "openai/clip-vit-base-patch32"
    },
    "audio": {
      "enabled": true,
      "auto_analyze": false
    },
    "search": {
      "enabled": true
    },
    "edit": {
      "enabled": true
    },
    "export": {
      "enabled": true
    }
  },
  "whisper": {
    "model_size": "auto",
    "device": "auto",
    "use_onnx": true
  },
  "embeddings": {
    "backend": "onnx",
    "device": "auto"
  }
}
```

[Files]
Create new device detection utilities, update config handling, modify agent implementations, and update model loading across the codebase.

**New Files to Create:**

1. `backend/utils/__init__.py` - Utilities package init
2. `backend/utils/device.py` - Device detection and configuration (200 lines)
3. `backend/utils/model_loader.py` - Centralized ONNX model loading utilities (150 lines)

**Files to Modify:**

1. `backend/config.json` - Add device and agents configuration sections
2. `backend/requirements.txt` - Add open-clip-torch, librosa, torch dependencies
3. `backend/agents/transcription_agent.py` - Replace transformers.pipeline with ONNX Runtime
4. `backend/pipeline/vectorizer.py` - Add ONNX backend support for sentence-transformers
5. `backend/agents/color_agent.py` - Un-stub, implement CLIP-based analysis
6. `backend/agents/audio_agent.py` - Un-stub, implement librosa-based analysis
7. `backend/app.py` - Add device detection on startup, conditional agent registration
8. `backend/orchestrator/orchestrator.py` - Update to handle agent-disabled scenarios
9. `backend/timeline/schema.py` - Add new EffectType enums for color/audio effects

**Files to Update (Minor Changes):**

1. `backend/agents/base.py` - Verify progress callback support
2. `backend/agents/registry.py` - Add agent enabled/disabled tracking
3. `backend/media/ffmpeg_wrapper.py` - Verify extract_frame() function exists

[Functions]
Implement device detection, model loading utilities, agent analysis methods, and configuration validation functions.

**New Functions in backend/utils/device.py:**

```python
def detect_device() -> DeviceConfig:
    """
    Detect available hardware and return optimal configuration.
    
    Priority: CUDA > Apple Silicon (MPS) > CPU
    Returns DeviceConfig with device_type and onnx_providers list.
    """

def get_onnx_providers(cuda_enabled: bool = True) -> list[str]:
    """
    Get ordered list of ONNX Runtime providers based on availability.
    
    Checks onnxruntime.get_available_providers() and returns prioritized list.
    Falls back gracefully if GPU providers unavailable.
    """

def get_torch_device() -> str:
    """
    Get PyTorch device string for models not using ONNX.
    
    Returns: "cuda", "mps", or "cpu"
    """

def log_device_info(config: DeviceConfig) -> None:
    """Log detected device information for debugging."""
```

**New Functions in backend/utils/model_loader.py:**

```python
def load_whisper_onnx(model_size: str, providers: list[str]) -> Any:
    """
    Load Whisper model via ONNX Runtime using Optimum.
    
    Args:
        model_size: "tiny", "base", "small", "medium", "large-v3"
        providers: ONNX execution providers list
    
    Returns:
        ORTModelForSpeechSeq2Seq instance
    """

def load_clip_onnx(model_name: str, providers: list[str]) -> tuple:
    """
    Load CLIP model for visual analysis.
    
    Args:
        model_name: HuggingFace model identifier
        providers: ONNX execution providers
    
    Returns:
        (model, processor) tuple
    """

def load_sentence_transformer_onnx(model_name: str, device: str) -> Any:
    """
    Load sentence-transformers model with ONNX backend.
    
    Args:
        model_name: Model identifier
        device: "cuda", "mps", or "cpu"
    
    Returns:
        SentenceTransformer instance with backend="onnx"
    """
```

**Modified Functions in backend/agents/transcription_agent.py:**

```python
def _get_whisper(model_size: str = "small", device_config: DeviceConfig = None) -> Any:
    """
    Load Whisper model via ONNX Runtime (MODIFIED).
    
    Changes:
    - Import from optimum.onnxruntime instead of transformers
    - Use ORTModelForSpeechSeq2Seq.from_pretrained() with export=True
    - Pass providers=device_config.onnx_providers for GPU acceleration
    - Create pipeline with ONNX model
    """
```

**New Functions in backend/agents/color_agent.py:**

```python
async def analyze_all(self) -> ToolResult:
    """
    Analyze all segments with CLIP embeddings.
    
    For each segment:
    1. Extract keyframe at segment.start using ffmpeg
    2. Run CLIP inference to get embedding
    3. Detect brightness, dominant color from RGB values
    4. Store in layers["color_agent"][segment_id]
    5. Add to ChromaDB chroma/visual collection
    
    Returns ToolResult with processed count
    """

def _extract_keyframe(self, segment_id: str) -> str:
    """
    Extract keyframe image for a segment.
    
    Uses media.ffmpeg_wrapper.extract_frame() at segment.start timecode.
    Returns path to temporary JPEG file.
    """

def _analyze_image(self, image_path: str) -> dict:
    """
    Run CLIP inference and color analysis on image.
    
    Returns dict with:
    - clip_embedding: list[float] (512-dim vector)
    - brightness: float (0.0-1.0)
    - dominant_color: str (hex color code)
    - saturation: float (0.0-1.0)
    """
```

**New Functions in backend/agents/audio_agent.py:**

```python
async def analyze_all(self) -> ToolResult:
    """
    Analyze all segments with librosa audio features.
    
    For each segment:
    1. Extract audio chunk (segment.start → segment.end)
    2. Compute RMS energy, pitch, speech rate
    3. Store in layers["audio_agent"][segment_id]
    4. Add feature vector to ChromaDB chroma/audio
    
    Returns ToolResult with processed count
    """

def _extract_audio_features(self, segment_id: str) -> dict:
    """
    Extract audio features using librosa.
    
    Returns dict with:
    - energy_rms: float (0.0-1.0)
    - pitch_hz: float (fundamental frequency)
    - speech_rate_wps: float (words per second)
    - spectral_centroid: float
    """
```

**Modified Functions in backend/app.py:**

```python
def _create_project_context(project_id: str) -> dict:
    """
    Create project context with conditional agent registration (MODIFIED).
    
    Changes:
    - Call detect_device() before creating agents
    - Check config["agents"][agent_name]["enabled"] before registry.register()
    - Pass device_config to agent constructors
    - Conditionally register ColorAgent and AudioAgent based on flags
    """

def warmup_models():
    """
    Pre-load models at startup (MODIFIED).
    
    Changes:
    - Use ONNX Runtime model loaders
    - Pass detected device configuration
    - Pre-load CLIP and librosa if agents enabled
    """
```

[Classes]
Update agent base classes, extend configuration handling classes, and add device-aware model managers.

**Modified Classes:**

```python
# backend/agents/base.py
class BaseAgent(ABC):
    """
    Base class for all agents (MINOR UPDATE).
    
    Changes:
    - Add device_config parameter to __init__
    - Store device_config as instance variable for use in model loading
    """

# backend/agents/color_agent.py
class ColorAgent(BaseAgent):
    """
    Visual analysis agent using CLIP embeddings (MAJOR REWRITE).
    
    Changes:
    - Remove stub implementation
    - Add _clip_model and _processor instance variables
    - Implement lazy model loading with ONNX Runtime
    - Add analyze_all() method for batch processing
    - Implement _extract_keyframe() and _analyze_image() helpers
    - Add tool: color.analyze_all for orchestrator integration
    - Add tool: color.add_effect for applying color effects
    """

# backend/agents/audio_agent.py
class AudioAgent(BaseAgent):
    """
    Audio analysis agent using librosa (MAJOR REWRITE).
    
    Changes:
    - Remove stub implementation
    - Add _sample_rate constant (22050 Hz)
    - Implement lazy librosa loading
    - Add analyze_all() method for batch processing
    - Implement _extract_audio_features() helper
    - Add tool: audio.analyze_all for orchestrator integration
    - Add tool: audio.add_effect for applying audio effects
    """

# backend/agents/registry.py
class AgentRegistry:
    """
    Agent registry with enabled/disabled tracking (MINOR UPDATE).
    
    Changes:
    - Add _disabled_agents: set[str] tracking
    - Add is_enabled(agent_name: str) -> bool method
    - Filter registered_tool_names() to exclude disabled agents
    - Add enable_agent() and disable_agent() methods
    """
```

**New Classes:**

```python
# backend/utils/device.py
class DeviceDetector:
    """
    Singleton device detection manager.
    
    Methods:
    - get_instance() -> DeviceDetector (singleton)
    - detect() -> DeviceConfig (run detection)
    - get_config() -> DeviceConfig (cached result)
    - refresh() -> DeviceConfig (re-run detection)
    """

# backend/utils/model_loader.py
class ModelCache:
    """
    Global model cache for ONNX models.
    
    Prevents reloading models across multiple requests.
    Thread-safe singleton pattern.
    
    Methods:
    - get(key: str) -> Any | None
    - set(key: str, model: Any) -> None
    - clear() -> None
    - list_loaded() -> list[str]
    """
```

[Dependencies]
Add ONNX Runtime GPU support, CLIP models, audio analysis libraries, and explicit PyTorch with CUDA support.

**Dependencies to Add to requirements.txt:**

```txt
# ── GPU acceleration (CUDA + Apple Silicon) ──────────────────────────────────
# PyTorch with CUDA support (if available) or CPU fallback
torch>=2.0.0
torchvision>=0.15.0

# ONNX Runtime with GPU support
# Note: onnxruntime-gpu requires CUDA 11.8+ on Windows/Linux
# For Apple Silicon, use standard onnxruntime (supports CoreML)
# onnxruntime-gpu>=1.18.0  # Uncomment on CUDA systems, comment out optimum[onnxruntime] above

# ── Visual analysis (CLIP) ────────────────────────────────────────────────────
open-clip-torch>=2.24.0
Pillow>=10.0.0  # Image processing for CLIP

# ── Audio analysis ────────────────────────────────────────────────────────────
librosa>=0.10.0
soundfile>=0.12.0  # Required by librosa for audio file I/O
```

**Installation Instructions to Add:**

```bash
# For CUDA systems (Windows/Linux with NVIDIA GPU):
pip uninstall onnxruntime onnxruntime-gpu  # Clean slate
pip install onnxruntime-gpu>=1.18.0
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# For Apple Silicon (Mac M1/M2/M3):
pip install torch torchvision  # Apple Silicon optimized
pip install onnxruntime  # Includes CoreML support

# For CPU-only systems:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install onnxruntime
```

**Dependency Verification Script:**

Create `backend/check_gpu.py` to verify GPU acceleration:

```python
import torch
import onnxruntime as ort

print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("CUDA device:", torch.cuda.get_device_name(0))

print("\nONNX Runtime providers:")
for p in ort.get_available_providers():
    print(f"  - {p}")
```

[Testing]
Create device detection tests, model loading tests, agent integration tests, and end-to-end pipeline validation.

**New Test Files:**

1. `backend/tests/test_device_detection.py` - Test device detection logic
2. `backend/tests/test_onnx_loading.py` - Test ONNX model loading
3. `backend/tests/test_color_agent.py` - Test ColorAgent analysis
4. `backend/tests/test_audio_agent.py` - Test AudioAgent analysis
5. `backend/tests/test_agent_config.py` - Test agent enable/disable

**Test Cases:**

```python
# test_device_detection.py
def test_detect_device_cuda():
    """Test CUDA detection when available."""
    
def test_detect_device_fallback():
    """Test CPU fallback when no GPU."""
    
def test_onnx_providers_ordering():
    """Test provider list ordering is correct."""

# test_onnx_loading.py
def test_load_whisper_onnx():
    """Test Whisper loads via ONNX Runtime."""
    
def test_load_clip_onnx():
    """Test CLIP loads with correct providers."""
    
def test_model_cache():
    """Test ModelCache singleton behavior."""

# test_color_agent.py
def test_color_analyze_segment():
    """Test single segment CLIP analysis."""
    
def test_color_batch_analysis():
    """Test analyze_all() processes all segments."""
    
def test_keyframe_extraction():
    """Test FFmpeg keyframe extraction."""

# test_audio_agent.py
def test_audio_feature_extraction():
    """Test librosa feature extraction."""
    
def test_audio_batch_analysis():
    """Test analyze_all() processes all segments."""

# test_agent_config.py
def test_agent_disabled_not_registered():
    """Test disabled agents aren't registered."""
    
def test_auto_analyze_flag():
    """Test auto_analyze flag prevents automatic analysis."""
```

**Manual Testing Checklist:**

- [ ] Verify CUDA detection on Windows with NVIDIA GPU
- [ ] Verify Apple Silicon (MPS) detection on Mac M1/M2
- [ ] Verify CPU fallback on systems without GPU
- [ ] Test Whisper transcription speed with ONNX Runtime vs PyTorch
- [ ] Test CLIP analysis on video segments
- [ ] Test librosa audio feature extraction
- [ ] Test agent enable/disable flags in config.json
- [ ] Test auto_analyze flag prevents automatic ColorAgent/AudioAgent runs
- [ ] Verify ChromaDB collections: chroma/text, chroma/visual, chroma/audio
- [ ] Test semantic search with "find bright outdoor scenes"
- [ ] Test semantic search with "find loud moments"

[Implementation Order]
Implement changes in sequence to minimize conflicts and enable incremental testing at each stage.

**Phase 1: Device Detection Foundation (No Breaking Changes)**

1. Create `backend/utils/__init__.py` (empty package init)
2. Create `backend/utils/device.py` with DeviceDetector class
3. Create `backend/utils/model_loader.py` with ModelCache class
4. Add device detection tests
5. Test device detection in isolation (run `python -c "from utils.device import detect_device; print(detect_device())"`)

**Phase 2: Configuration Schema Extension**

6. Update `backend/config.json` with device and agents sections
7. Add config validation in app.py startup
8. Test config loading and validation
9. Update ARCHITECTURE.md with new config schema

**Phase 3: ONNX Runtime Migration for Existing Agents**

10. Update `backend/requirements.txt` with torch, onnxruntime-gpu
11. Modify `backend/agents/transcription_agent.py` to use ONNX Runtime
    - Import from optimum.onnxruntime
    - Replace transformers.pipeline() with ORTModelForSpeechSeq2Seq
    - Pass onnx_providers from device config
12. Modify `backend/pipeline/vectorizer.py` to use ONNX backend
    - Add backend="onnx" parameter to SentenceTransformer
    - Pass device from config
13. Test transcription with ONNX Runtime (compare speed vs PyTorch)
14. Test vectorization with ONNX backend

**Phase 4: ColorAgent Implementation**

15. Add open-clip-torch, Pillow to requirements.txt
16. Verify `backend/media/ffmpeg_wrapper.py` has extract_frame() function
17. Implement ColorAgent.analyze_all() in `backend/agents/color_agent.py`
18. Implement ColorAgent._extract_keyframe() helper
19. Implement ColorAgent._analyze_image() with CLIP
20. Add color.analyze_all tool declaration
21. Create chroma/visual collection setup
22. Test ColorAgent on sample video segments
23. Verify CLIP embeddings stored in ChromaDB

**Phase 5: AudioAgent Implementation**

24. Add librosa, soundfile to requirements.txt
25. Implement AudioAgent.analyze_all() in `backend/agents/audio_agent.py`
26. Implement AudioAgent._extract_audio_features() with librosa
27. Add audio.analyze_all tool declaration
28. Create chroma/audio collection setup
29. Test AudioAgent on sample video segments
30. Verify audio features stored in ChromaDB

**Phase 6: Agent Registration and Orchestrator Integration**

31. Update `backend/agents/registry.py` with enabled/disabled tracking
32. Modify `backend/app.py` _create_project_context():
    - Call detect_device() at startup
    - Conditional agent registration based on config["agents"][name]["enabled"]
    - Pass device_config to agent constructors
33. Update `backend/app.py` warmup_models():
    - Use ONNX model loaders
    - Conditionally pre-load ColorAgent and AudioAgent models
34. Update `backend/orchestrator/orchestrator.py`:
    - Handle cases where agents are disabled
    - Filter tools from disabled agents
35. Test full pipeline with all agents enabled
36. Test pipeline with ColorAgent disabled
37. Test pipeline with AudioAgent disabled

**Phase 7: Effects Integration (Color and Audio)**

38. Add new EffectType enums to `backend/timeline/schema.py`:
    - EffectType.BRIGHTNESS_ADJUST
    - EffectType.CONTRAST_ADJUST  
    - EffectType.COLOR_OVERLAY
    - EffectType.AUDIO_NORMALIZE
    - EffectType.REVERB
39. Add color.add_effect and audio.add_effect tools to respective agents
40. Update `backend/media/effect_compiler.py` to handle new effect types
41. Test effect compilation in FFmpeg filter_complex

**Phase 8: Auto-Analysis Integration**

42. Update `backend/app.py` upload_video():
    - After auto-transcription completes
    - If config["agents"]["color"]["auto_analyze"]: run ColorAgent.analyze_all()
    - If config["agents"]["audio"]["auto_analyze"]: run AudioAgent.analyze_all()
43. Add background threads for async analysis
44. Test auto-analysis flag behavior
45. Verify analysis runs in background without blocking upload response

**Phase 9: Testing and Documentation**

46. Run all unit tests
47. Run manual testing checklist
48. Create `backend/check_gpu.py` verification script
49. Update ARCHITECTURE.md with new agent capabilities
50. Update README.md with installation instructions for CUDA/Apple Silicon
51. Add GPU acceleration section to docs
52. Create performance comparison benchmarks (ONNX vs PyTorch)

**Phase 10: Validation and Cleanup**

53. Test on Windows with NVIDIA GPU (CUDA)
54. Test on Mac with Apple Silicon (MPS)
55. Test on CPU-only system (fallback)
56. Verify all ChromaDB collections work correctly
57. Verify semantic search across all modalities
58. Profile memory usage and optimize if needed
59. Add logging for device detection and model loading
60. Final code review and cleanup
