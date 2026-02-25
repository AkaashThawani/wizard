# 🧙 Wizard - AI Video Editor

An intelligent video editing system powered by AI agents that automatically transcribes, analyzes, and edits videos using natural language commands.

## ✨ Features

- **🎤 Whisper Transcription** - GPU-accelerated speech-to-text with CUDA
- **🔍 Visual Analysis** - CLIP-based scene understanding and search
- **🤖 AI-Powered Editing** - Natural language commands for video editing
- **📝 Smart Segmentation** - Automatic sentence-boundary detection
- **💬 Conversational Interface** - Chat with your video content
- **⚡ GPU Acceleration** - Optimized for NVIDIA GPUs (CPU fallback available)

---

## 📋 Prerequisites

Before installation, ensure you have:

- **Python 3.10+**
- **FFmpeg** (required for video processing)
  - Windows: `choco install ffmpeg` or `scoop install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- **Node.js 18+** (for frontend)
- **NVIDIA GPU** (optional, for faster processing)

---

## 🚀 Quick Start

### 1. Install Backend (Automated)

The installer will automatically:
- ✅ Check for FFmpeg
- ✅ Create virtual environment (`.venv`)
- ✅ Detect GPU and install appropriate packages
- ✅ Download ONNX models (~500 MB, one-time download)

```bash
cd backend
python install.py
```

**Note:** ONNX models are automatically downloaded during installation. You don't need Git LFS.

### 2. Activate Virtual Environment

**Windows PowerShell:**
```bash
.venv\Scripts\Activate.ps1
```

**Windows CMD:**
```bash
.venv\Scripts\activate.bat
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### 3. Setup Frontend

```bash
cd ../frontend
npm install
```

---

## 🎬 Running the Application

### Terminal 1: Start Backend Server

```bash
cd backend
# Activate venv first (see above)
python app.py
```

Backend will start on `http://localhost:5001`

### Terminal 2: Start Frontend Dev Server

```bash
cd frontend
npm run dev
```

Frontend will start on `http://localhost:5173`

### Open in Browser

Navigate to `http://localhost:5173` and start editing!

---

## 📁 Project Structure

```
wizard/
├── backend/              # Python API server
│   ├── agents/           # AI agents (transcription, color, audio, etc.)
│   ├── llm/              # LLM client and prompts
│   ├── media/            # FFmpeg wrapper and video processing
│   ├── orchestrator/     # LangGraph workflow orchestration
│   ├── pipeline/         # Data processing pipeline
│   ├── timeline/         # Timeline state management
│   ├── utils/            # Device detection, model loading
│   ├── app.py            # Flask/FastAPI server
│   ├── install.py        # Automated installer ⭐ NEW
│   ├── setup.py          # GPU-aware package installation
│   ├── config.json       # Agent configuration
│   └── .env.example      # Environment template
│
├── frontend/             # React + TypeScript app
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── hooks/        # Custom hooks (SSE, WebSocket)
│   │   ├── api/          # API client
│   │   └── types/        # TypeScript types
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                 # Detailed documentation
│   ├── ARCHITECTURE.md
│   └── FILE_STRUCTURE.md
│
└── projects/             # Video projects data (auto-created)
```

---

## 🛠️ Tech Stack

### Backend
- **Python 3.10+** - Core language
- **FastAPI** - Modern API framework
- **PyTorch** - Deep learning with CUDA support
- **ONNX Runtime** - Optimized inference (CPU/GPU)
- **Whisper** - Speech recognition (OpenAI)
- **CLIP** - Visual understanding (OpenAI)
- **ChromaDB** - Vector database for embeddings
- **LangGraph** - AI agent orchestration

### Frontend
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool with HMR
- **Server-Sent Events** - Real-time updates

---

## 🎯 Usage Example

1. **Upload a video** through the web interface
2. **Wait for automatic analysis**:
   - Whisper transcription (GPU-accelerated)
   - Sentence segmentation
   - Visual analysis with CLIP
   - Vector embedding generation
3. **Chat with your video**:
   - "Remove all filler words like 'um' and 'uh'"
   - "Cut out the pauses longer than 2 seconds"
   - "Find scenes about [topic]"
   - "Export the final video"

---

## 🔧 Configuration

### GPU Configuration

The system automatically detects and configures GPU support:
- **NVIDIA GPU** → CUDA acceleration for Whisper + ONNX Runtime GPU
- **CPU Only** → Stable CPU-only mode for all models

Verify GPU detection:
```bash
cd backend
python check_gpu.py
```

### Environment Variables

Create `backend/.env` file:

```env
# LLM Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here

# Or use local model
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3
```

---

## 📖 Documentation

Detailed documentation is available in the [`docs/`](docs/) folder:

- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [File Structure](docs/FILE_STRUCTURE.md) - Project organization

---

## 🐛 Troubleshooting

### FFmpeg Not Found

The installer will check for FFmpeg. If missing:

```bash
# Windows (Chocolatey)
choco install ffmpeg

# Windows (Scoop)
scoop install ffmpeg

# macOS
brew install ffmpeg

# Linux (Ubuntu/Debian)
sudo apt install ffmpeg
```

### GPU Not Detected

```bash
# Check NVIDIA GPU
nvidia-smi

# Verify installation
cd backend
python check_gpu.py
```

### Import Errors

Make sure you're in the virtual environment:
```bash
# Check if venv is active (you should see (.venv) in prompt)
# If not, activate it:
cd backend
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux
```

### Port 5001 Already in Use (macOS)

If port 5001 is already in use, you can specify a custom port:

```bash
# Set custom port
export PORT=5002
python app.py
```

Then update the frontend proxy in `frontend/vite.config.ts`:
```typescript
target: 'http://localhost:5002',
```

**Note:** Port 5000 is reserved by AirPlay Receiver on macOS Monterey+, which is why we use 5001 by default.

---

## 🏗️ Development Phases

- ✅ **Phase 1**: Backend migration to `/backend`
- ✅ **Phase 2**: React + TypeScript frontend with Vite
- ✅ **Phase 3**: AI agent orchestration with LangGraph
- ✅ **Phase 4**: GPU acceleration (CUDA + ONNX)
- ✅ **Phase 5**: Automated installation system

---

---

## 🤝 Contributing

Contributions are welcome! Please read the documentation in the `docs/` folder before contributing.

---

## 📧 Support

For issues and questions, please open an issue on GitHub.

---

