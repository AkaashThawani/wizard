import type { Segment } from './api';

export interface VideoPlayerProps {
  projectId: string | null;
  className?: string;
}

export interface TimelineProps {
  segments: Segment[];
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
  onSegmentClick: (segmentId: string) => void;
  className?: string;
}

export interface TimelineControlsProps {
  isPlaying: boolean;
  onTogglePlay: () => void;
  onExport: () => void;
  isExporting: boolean;
  disabled?: boolean;
  className?: string;
}

export interface SegmentBlockProps {
  segment: Segment;
  index: number;
  totalDuration: number;
  onClick: (segmentId: string) => void;
}

export interface ChatPanelProps {
  projectId: string | null;
  className?: string;
}

export interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number | null;
  error?: boolean;
  className?: string;
}

export interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export interface TranscriptionPanelProps {
  segments: Segment[];
  showFull: boolean;
  onToggleFull: (show: boolean) => void;
  onSegmentClick: (segmentId: string) => void;
  className?: string;
}

export interface TranscriptionItemProps {
  segment: Segment;
  onClick: (segmentId: string) => void;
  className?: string;
}

export interface AppHeaderProps {
  projectId: string | null;
  onNewProject: () => void;
  onClearProject: () => void;
  onUpload: (file: File) => void;
  className?: string;
}
