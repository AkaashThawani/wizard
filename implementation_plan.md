# Implementation Plan: Wizard Frontend Redesign

## [Overview]
Complete rewrite of the Wizard video editing frontend using modern React best practices, shadcn/ui component library, Tailwind CSS, and TanStack Query + Zustand for state management to minimize custom code and improve maintainability.

The current frontend has ~700 lines of monolithic App.tsx with custom CSS and direct state management. The redesign will modularize the application into reusable components, leverage battle-tested UI libraries, standardize server state management (SSE/WebSocket), and follow React 19 best practices. This will reduce custom code by ~60%, improve type safety, enhance accessibility, and create a more maintainable codebase.

The application will maintain all existing functionality (video upload, AI chat, timeline editing, transcription viewing, export) while improving UX with better loading states, error handling, and responsive design. The new architecture separates concerns: TanStack Query handles all server state (API calls, SSE, WebSocket), Zustand manages UI state (playback, selections, UI toggles), and shadcn/ui provides accessible, customizable components.

## [Types]
Type system updates to support new state management architecture and component props.

**New Type Definitions:**

```typescript
// src/types/store.ts - Zustand store types
export interface VideoPlayerState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  virtualTime: number;
  volume: number;
  muted: boolean;
}

export interface UIState {
  selectedSegmentId: string | null;
  expandedPanels: Set<string>;
  showFullTranscription: boolean;
  sidebarCollapsed: boolean;
}

export interface ProjectState {
  projectId: string | null;
  videoBlobUrl: string | null;
}

export interface WizardStore {
  player: VideoPlayerState;
  ui: UIState;
  project: ProjectState;
  // Actions
  setPlaying: (playing: boolean) => void;
  setCurrentTime: (time: number) => void;
  togglePanel: (panelId: string) => void;
  selectSegment: (segmentId: string | null) => void;
  setProject: (projectId: string | null) => void;
  // ... more actions
}

// src/types/queries.ts - TanStack Query types
export interface UseTimelineOptions {
  projectId: string | null;
  enabled?: boolean;
}

export interface UseSSEOptions {
  projectId: string;
  onEvent?: (event: SSEEvent) => void;
}

export interface UseChatOptions {
  projectId: string | null;
  enabled?: boolean;
}

// src/types/components.ts - Component prop types
export interface VideoPlayerProps {
  projectId: string | null;
  className?: string;
}

export interface TimelineProps {
  segments: Segment[];
  currentTime: number;
  onSeek: (time: number) => void;
  onSegmentClick: (segmentId: string) => void;
}

export interface ChatPanelProps {
  projectId: string | null;
  className?: string;
}
```

**Updated Existing Types:**
- Keep all types in `src/types/api.ts` as-is (already well-structured)
- Add `className?: string` to all component interfaces for Tailwind composition

## [Files]
Complete file structure transformation from monolithic to modular architecture.

**New Files to Create:**

Configuration & Setup:
- `frontend/tailwind.config.js` - Tailwind CSS configuration with custom theme
- `frontend/components.json` - shadcn/ui configuration
- `frontend/postcss.config.js` - PostCSS configuration for Tailwind
- `frontend/src/lib/utils.ts` - cn() utility for Tailwind class merging

Store & State Management:
- `frontend/src/store/useWizardStore.ts` - Zustand store definition
- `frontend/src/store/selectors.ts` - Memoized store selectors
- `frontend/src/types/store.ts` - Store type definitions
- `frontend/src/types/queries.ts` - TanStack Query types
- `frontend/src/types/components.ts` - Component prop types

TanStack Query Hooks:
- `frontend/src/queries/useProjects.ts` - Project CRUD operations
- `frontend/src/queries/useTimeline.ts` - Timeline data fetching
- `frontend/src/queries/useSSE.ts` - SSE connection (refactored)
- `frontend/src/queries/useChat.ts` - WebSocket chat (refactored)
- `frontend/src/queries/queryClient.ts` - Query client configuration

shadcn/ui Components (via CLI):
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/textarea.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/scroll-area.tsx`
- `frontend/src/components/ui/separator.tsx`
- `frontend/src/components/ui/toast.tsx`
- `frontend/src/components/ui/toaster.tsx`
- `frontend/src/components/ui/use-toast.ts`
- `frontend/src/components/ui/dialog.tsx`
- `frontend/src/components/ui/progress.tsx`
- `frontend/src/components/ui/skeleton.tsx`
- `frontend/src/components/ui/collapsible.tsx`

Custom Feature Components:
- `frontend/src/components/layout/AppHeader.tsx` - Top header with logo, project ID, actions
- `frontend/src/components/layout/AppLayout.tsx` - Main layout grid container
- `frontend/src/components/layout/Sidebar.tsx` - Right sidebar container
- `frontend/src/components/video/VideoPlayer.tsx` - Video player component
- `frontend/src/components/video/VideoControls.tsx` - Play/pause, volume controls
- `frontend/src/components/timeline/Timeline.tsx` - Timeline visualization
- `frontend/src/components/timeline/TimelineControls.tsx` - Timeline header controls
- `frontend/src/components/timeline/SegmentBlock.tsx` - Individual segment block
- `frontend/src/components/timeline/Playhead.tsx` - Playhead indicator
- `frontend/src/components/chat/ChatPanel.tsx` - Chat interface (refactored)
- `frontend/src/components/chat/ChatMessage.tsx` - Individual message bubble
- `frontend/src/components/chat/ChatInput.tsx` - Message input with send button
- `frontend/src/components/transcription/TranscriptionPanel.tsx` - Transcription list panel
- `frontend/src/components/transcription/TranscriptionItem.tsx` - Individual transcription item
- `frontend/src/components/edits/EditDecisionsPanel.tsx` - Edit decisions panel
- `frontend/src/components/upload/UploadButton.tsx` - Video upload button component

**Files to Modify:**

Root Files:
- `frontend/package.json` - Add new dependencies
- `frontend/vite.config.ts` - Add path alias for @/ imports
- `frontend/tsconfig.json` - Add path alias configuration
- `frontend/index.html` - Update for better contrast/readability

Entry Point:
- `frontend/src/main.tsx` - Wrap with QueryClientProvider, Toaster
- `frontend/src/index.css` - Replace with Tailwind directives

Core Application:
- `frontend/src/App.tsx` - Complete rewrite: use new components, remove business logic
- `frontend/src/App.css` - DELETE (replaced by Tailwind)

API Client:
- `frontend/src/api/client.ts` - Minor refactor for better error handling

Existing Hooks:
- `frontend/src/hooks/useSSE.ts` - Refactor into TanStack Query hook
- `frontend/src/hooks/useWebSocket.ts` - Refactor into TanStack Query hook

**Files to Delete:**
- `frontend/src/App.css` - All styling moved to Tailwind
- `frontend/src/components/ChatInterface.css` - Component-specific CSS replaced
- `frontend/src/hooks/useSSE.example.tsx` - Unused example file

**Directory Structure (After Changes):**
```
frontend/src/
├── api/
│   └── client.ts (modified)
├── assets/
│   └── react.svg
├── components/
│   ├── ui/ (NEW - shadcn/ui components)
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── ... (14 components)
│   ├── layout/ (NEW)
│   │   ├── AppHeader.tsx
│   │   ├── AppLayout.tsx
│   │   └── Sidebar.tsx
│   ├── video/ (NEW)
│   │   ├── VideoPlayer.tsx
│   │   └── VideoControls.tsx
│   ├── timeline/ (NEW)
│   │   ├── Timeline.tsx
│   │   ├── TimelineControls.tsx
│   │   ├── SegmentBlock.tsx
│   │   └── Playhead.tsx
│   ├── chat/ (NEW)
│   │   ├── ChatPanel.tsx
│   │   ├── ChatMessage.tsx
│   │   └── ChatInput.tsx
│   ├── transcription/ (NEW)
│   │   ├── TranscriptionPanel.tsx
│   │   └── TranscriptionItem.tsx
│   ├── edits/ (NEW)
│   │   └── EditDecisionsPanel.tsx
│   └── upload/ (NEW)
│       └── UploadButton.tsx
├── hooks/ (kept for compatibility)
│   └── ... (migrated to queries/)
├── lib/ (NEW)
│   └── utils.ts
├── queries/ (NEW)
│   ├── queryClient.ts
│   ├── useProjects.ts
│   ├── useTimeline.ts
│   ├── useSSE.ts
│   └── useChat.ts
├── store/ (NEW)
│   ├── useWizardStore.ts
│   └── selectors.ts
├── types/
│   ├── api.ts (unchanged)
│   ├── store.ts (NEW)
│   ├── queries.ts (NEW)
│   └── components.ts (NEW)
├── App.tsx (complete rewrite)
├── main.tsx (modified)
└── index.css (replaced)
```

## [Functions]
Key function signatures and implementations for state management and data fetching.

**New Functions:**

Store Actions (src/store/useWizardStore.ts):
```typescript
// Zustand store with actions
const useWizardStore = create<WizardStore>((set, get) => ({
  player: { isPlaying: false, currentTime: 0, ... },
  ui: { selectedSegmentId: null, expandedPanels: new Set(), ... },
  project: { projectId: null, videoBlobUrl: null },
  
  // Player actions
  setPlaying: (playing: boolean) => set((state) => ({ 
    player: { ...state.player, isPlaying: playing } 
  })),
  setCurrentTime: (time: number) => set((state) => ({ 
    player: { ...state.player, currentTime: time } 
  })),
  
  // UI actions
  togglePanel: (panelId: string) => set((state) => {
    const panels = new Set(state.ui.expandedPanels);
    if (panels.has(panelId)) panels.delete(panelId);
    else panels.add(panelId);
    return { ui: { ...state.ui, expandedPanels: panels } };
  }),
  
  // Project actions
  setProject: (projectId: string | null) => {
    set({ project: { projectId, videoBlobUrl: null } });
    if (projectId) localStorage.setItem('wizard_project_id', projectId);
    else localStorage.removeItem('wizard_project_id');
  },
  // ... more actions
}));
```

Query Hooks (src/queries/):
```typescript
// useTimeline.ts
export function useTimeline(options: UseTimelineOptions) {
  const { projectId, enabled = true } = options;
  return useQuery({
    queryKey: ['timeline', projectId],
    queryFn: () => api.getTimeline(projectId!),
    enabled: enabled && !!projectId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}

// useProjects.ts
export function useCreateProject() {
  const queryClient = useQueryClient();
  const store = useWizardStore();
  
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: (data) => {
      store.setProject(data.project_id);
      queryClient.invalidateQueries({ queryKey: ['timeline'] });
    },
  });
}

export function useUploadVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, file }: { projectId: string; file: File }) =>
      api.uploadVideo(projectId, file),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['timeline', variables.projectId] });
    },
  });
}

// useSSE.ts - Refactored to use TanStack Query subscriptions
export function useSSE(options: UseSSEOptions) {
  const { projectId, onEvent } = options;
  const queryClient = useQueryClient();
  
  useEffect(() => {
    if (!projectId) return;
    
    const eventSource = api.createSSE(projectId);
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onEvent?.(data);
      
      // Auto-invalidate timeline on specific events
      if (data.event === 'prompt_done' || 
          (data.event === 'stage' && data.data.stage === 'vectorize')) {
        queryClient.invalidateQueries({ queryKey: ['timeline', projectId] });
      }
    };
    
    return () => eventSource.close();
  }, [projectId, onEvent, queryClient]);
}

// useChat.ts - WebSocket with TanStack Query
export function useChat(options: UseChatOptions) {
  const { projectId, enabled = true } = options;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<'idle' | 'thinking'>('idle');
  const queryClient = useQueryClient();
  
  // Load history via Query
  const { data: history } = useQuery({
    queryKey: ['chat-history', projectId],
    queryFn: () => fetch(`http://localhost:5001/project/${projectId}/chat/history`)
      .then(r => r.json()),
    enabled: enabled && !!projectId,
  });
  
  // WebSocket connection
  useEffect(() => {
    // ... (similar to current implementation but cleaner)
    // Auto-invalidate timeline when assistant responds
  }, [projectId, enabled, queryClient]);
  
  return { messages, status, sendMessage };
}
```

Utility Functions (src/lib/utils.ts):
```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}
```

**Modified Functions:**

Timeline Calculations (move to utilities):
- `virtualToSource(vTime: number, sequence: Segment[]): number` - Extract from App.tsx
- `sourceToVirtual(sTime: number, sequence: Segment[]): number` - Extract from App.tsx
- These become pure functions in `src/lib/timeline-utils.ts`

## [Classes]
No new classes required. The application uses functional React components with hooks.

**Component Structure:**
All components are functional components using TypeScript and React hooks. They follow this pattern:

```typescript
interface ComponentProps {
  // Props typed in src/types/components.ts
}

export function Component({ prop1, prop2, className }: ComponentProps) {
  // Zustand store access
  const storeState = useWizardStore(selector);
  
  // TanStack Query hooks
  const { data, isLoading } = useQuery(...);
  
  // Local component state (if needed)
  const [localState, setLocalState] = useState();
  
  // Render with shadcn/ui components + Tailwind
  return (
    <div className={cn("base-classes", className)}>
      {/* ... */}
    </div>
  );
}
```

## [Dependencies]
New packages required for the redesign.

**Add to package.json:**

```json
{
  "dependencies": {
    "@radix-ui/react-collapsible": "^1.0.3",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-scroll-area": "^1.0.5",
    "@radix-ui/react-separator": "^1.0.3",
    "@radix-ui/react-slot": "^1.0.2",
    "@radix-ui/react-toast": "^1.1.5",
    "@tanstack/react-query": "^5.51.0",
    "@tanstack/react-query-devtools": "^5.51.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "lucide-react": "^0.400.0",
    "tailwind-merge": "^2.4.0",
    "tailwindcss-animate": "^1.0.7",
    "zustand": "^4.5.4"
  },
  "devDependencies": {
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.6"
  }
}
```

**Installation Commands:**
```bash
# Install base dependencies
npm install @tanstack/react-query @tanstack/react-query-devtools zustand

# Install Tailwind CSS
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Install shadcn/ui dependencies
npm install tailwindcss-animate class-variance-authority clsx tailwind-merge lucide-react

# Install Radix UI primitives (via shadcn/ui CLI)
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card input textarea badge scroll-area separator toast dialog progress skeleton collapsible
```

**Removed Dependencies:**
None - existing dependencies (react, react-dom, socket.io-client) are kept.

## [Testing]
Testing strategy for the redesigned application.

**Test Files to Create:**
- `frontend/src/components/__tests__/VideoPlayer.test.tsx` - Video player component tests
- `frontend/src/components/__tests__/Timeline.test.tsx` - Timeline rendering tests
- `frontend/src/components/__tests__/ChatPanel.test.tsx` - Chat functionality tests
- `frontend/src/store/__tests__/useWizardStore.test.ts` - Store action tests
- `frontend/src/queries/__tests__/useTimeline.test.ts` - Query hook tests

**Test Coverage Areas:**
1. **Component Rendering**: Verify components render with correct props
2. **User Interactions**: Test clicks, inputs, keyboard events
3. **State Management**: Verify Zustand store updates correctly
4. **Data Fetching**: Mock TanStack Query responses
5. **SSE/WebSocket**: Mock real-time connections
6. **Timeline Math**: Test virtualToSource/sourceToVirtual calculations

**Testing Libraries to Add:**
```json
{
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/user-event": "^14.5.2",
    "vitest": "^1.6.0",
    "@vitest/ui": "^1.6.0",
    "jsdom": "^24.1.0"
  }
}
```

**Manual Testing Checklist:**
1. Upload video and verify transcription
2. Send chat messages and verify timeline updates
3. Play video and verify segment jumping
4. Click segments in timeline/transcription
5. Export video and verify download
6. Test SSE reconnection (restart backend)
7. Test WebSocket reconnection
8. Test browser refresh (project persistence)
9. Test responsive design (resize window)
10. Test keyboard shortcuts (space for play/pause)

## [Implementation Order]
Step-by-step sequence to minimize conflicts and ensure smooth migration.

**Phase 1: Foundation Setup (Day 1)**
1. Install all dependencies (Tailwind, shadcn/ui, TanStack Query, Zustand)
2. Configure Tailwind CSS (tailwind.config.js, postcss.config.js)
3. Initialize shadcn/ui (components.json, src/lib/utils.ts)
4. Update tsconfig.json and vite.config.ts for path aliases (@/)
5. Replace src/index.css with Tailwind directives

**Phase 2: Type System (Day 1)**
6. Create src/types/store.ts with Zustand types
7. Create src/types/queries.ts with TanStack Query types
8. Create src/types/components.ts with component prop types
9. Keep existing src/types/api.ts unchanged

**Phase 3: State Management (Day 2)**
10. Create src/store/useWizardStore.ts with complete store
11. Create src/store/selectors.ts with memoized selectors
12. Create src/lib/timeline-utils.ts with pure timeline functions
13. Create src/queries/queryClient.ts with QueryClient configuration

**Phase 4: Query Hooks (Day 2-3)**
14. Create src/queries/useProjects.ts (create, upload mutations)
15. Create src/queries/useTimeline.ts (timeline query)
16. Refactor src/hooks/useSSE.ts → src/queries/useSSE.ts
17. Refactor src/hooks/useWebSocket.ts → src/queries/useChat.ts
18. Update src/api/client.ts with better error handling

**Phase 5: shadcn/ui Components (Day 3)**
19. Run shadcn-ui CLI to add all 14 components to src/components/ui/
20. Verify all components render correctly
21. Customize theme colors in tailwind.config.js (match current dark theme)

**Phase 6: Layout Components (Day 4)**
22. Create src/components/layout/AppLayout.tsx (grid structure)
23. Create src/components/layout/AppHeader.tsx (logo, actions)
24. Create src/components/layout/Sidebar.tsx (right panel container)

**Phase 7: Video Components (Day 4-5)**
25. Create src/components/video/VideoPlayer.tsx (video element + controls)
26. Create src/components/video/VideoControls.tsx (play/pause, volume)
27. Integrate with Zustand store for playback state

**Phase 8: Timeline Components (Day 5-6)**
28. Create src/components/timeline/TimelineControls.tsx (header controls)
29. Create src/components/timeline/SegmentBlock.tsx (segment rendering)
30. Create src/components/timeline/Playhead.tsx (playhead indicator)
31. Create src/components/timeline/Timeline.tsx (main timeline container)
32. Implement timeline math (virtualToSource, sourceToVirtual)

**Phase 9: Chat Components (Day 6-7)**
33. Create src/components/chat/ChatMessage.tsx (message bubble)
34. Create src/components/chat/ChatInput.tsx (input + send button)
35. Create src/components/chat/ChatPanel.tsx (messages + input container)
36. Integrate with WebSocket hook

**Phase 10: Sidebar Panels (Day 7)**
37. Create src/components/transcription/TranscriptionItem.tsx
38. Create src/components/transcription/TranscriptionPanel.tsx (with shadcn/ui Collapsible)
39. Create src/components/edits/EditDecisionsPanel.tsx
40. Create src/components/upload/UploadButton.tsx

**Phase 11: Main App Integration (Day 8)**
41. Update src/main.tsx with QueryClientProvider and Toaster
42. Rewrite src/App.tsx to use new components
43. Wire up all state management (Zustand + TanStack Query)
44. Remove old business logic from App.tsx
45. Delete src/App.css and src/components/ChatInterface.css

**Phase 12: Testing & Polish (Day 9-10)**
46. Test all user flows (upload, chat, edit, export)
47. Test SSE/WebSocket reconnection
48. Test browser refresh and project persistence
49. Fix any bugs or visual issues
50. Add loading states and error boundaries
51. Optimize performance (React.memo where needed)
52. Add keyboard shortcuts
53. Test responsive design
54. Update README.md with new architecture
55. Final QA and deployment

**Rollback Strategy:**
- Keep all old files until Phase 11 complete
- Use git feature branch: `git checkout -b frontend-redesign`
- Commit after each phase for easy rollback
- Keep src/App.tsx.backup until fully tested

**Success Criteria:**
- ✅ All existing features work identically
- ✅ Code reduced by ~60% (from ~700 lines to ~300 in App.tsx)
- ✅ Zero CSS custom files (all Tailwind)
- ✅ All components under 200 lines
- ✅ Type-safe throughout (no `any` types)
- ✅ SSE/WebSocket standardized with TanStack Query
- ✅ Accessible UI (WCAG AA compliant via shadcn/ui)
- ✅ Fast page loads (<1s initial render)
