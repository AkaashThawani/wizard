export interface Project {
  project_id: string;
  source?: string;
  duration?: number;
}

export interface Segment {
  id: string;
  start: number;
  end: number;
  duration: number;
  text: string;
  speaker?: string;
  topics?: string[];
  effects?: Effect[];
  trim?: {start: number; end: number};
  transition_in?: Transition;
}

export interface Transition {
  type: string;
  duration_s: number;
}

export interface Effect {
  type: string;
  params: Record<string, any>;
  enabled: boolean;
}

export interface TranscriptionSegment {
  id: string;
  start: number;
  end: number;
  text: string;
}

export interface TimelineData {
  project_id: string;
  source: {path: string; filename: string; duration: number} | null;
  segment_count: number;
  current_sequence: Segment[];
  transcription: TranscriptionSegment[];
  history: HistoryEntry[];
  snapshots: Snapshot[];
  layers?: {
    edit_agent?: Record<string, any>;
    [key: string]: any;
  };
}

export interface HistoryEntry {
  prompt: string;
  summary: string;
  snapshot_ref?: string;
}

export interface Snapshot {
  snap_id: string;
  timestamp: string;
}

export interface PromptResponse {
  success: boolean;
  prompt: string;
  summary: string;
  full_text?: string;
  tool_calls: ToolCall[];
  snap_id?: string;
  error?: string;
}

export interface ToolCall {
  name: string;
  params: Record<string, any>;
}

export interface SSEEvent {
  event: string;
  data: Record<string, any>;
}

export interface UploadResponse {
  project_id: string;
  source: string;
  duration: number;
  width: number;
  height: number;
  auto_transcribed?: boolean;
}
