# Wizard - New Structure Setup Guide

## ✅ Backend Migration Complete

All Python code has been moved to `/backend` directory and paths have been updated.

## Project Structure

```
wizard/
├── backend/              # Flask API server
│   ├── agents/
│   ├── llm/
│   ├── media/
│   ├── orchestrator/
│   ├── pipeline/
│   ├── timeline/
│   ├── app.py           # Flask server (updated paths)
│   ├── config.json
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/            # React + Vite app (you created this)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── projects/            # Video projects data
├── gui/                 # OLD vanilla JS (can delete after frontend works)
└── implementation_plan.md  # Complete implementation guide
```

## Quick Start

### 1. Test Backend

```bash
cd backend
python app.py
```

Backend should start on http://localhost:5000

### 2. Setup Frontend

```bash
cd frontend
npm install
npm install @tanstack/react-query zustand
```

### 3. Configure Vite Proxy

Edit `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/project': 'http://localhost:5000'
    }
  }
})
```

### 4. Start Frontend Dev Server

```bash
cd frontend
npm run dev
```

Frontend will be on http://localhost:5173

## Next Steps

Follow the `implementation_plan.md` to implement the React frontend:

1. **Phase 2**: Create TypeScript types (`src/types/api.ts`)
2. **Phase 3**: Build API client (`src/api/client.ts`)
3. **Phase 4**: Create React hooks (`src/hooks/`)
4. **Phase 5**: Build UI components (`src/components/`)
5. **Phase 6**: Apply styling (port from `gui/static/style.css`)

## Benefits of New Structure

✅ **Backend**: Organized in dedicated directory
✅ **Frontend**: Modern React + TypeScript
✅ **CORS**: Configured for dev server
✅ **Hot Reload**: Vite HMR for fast development
✅ **Type Safety**: Full TypeScript support
✅ **State Management**: TanStack Query + Zustand
✅ **SSE Fixed**: Proper React hooks for real-time updates

## Running Both

Terminal 1:
```bash
cd backend
python app.py
```

Terminal 2:
```bash
cd frontend  
npm run dev
```

Then open http://localhost:5173 in your browser!
