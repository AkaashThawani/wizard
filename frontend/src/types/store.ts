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
  // State slices
  player: VideoPlayerState;
  ui: UIState;
  project: ProjectState;
  
  // Player actions
  setPlaying: (playing: boolean) => void;
  setCurrentTime: (time: number) => void;
  setDuration: (duration: number) => void;
  setVirtualTime: (time: number) => void;
  setVolume: (volume: number) => void;
  setMuted: (muted: boolean) => void;
  
  // UI actions
  togglePanel: (panelId: string) => void;
  setPanelExpanded: (panelId: string, expanded: boolean) => void;
  selectSegment: (segmentId: string | null) => void;
  setShowFullTranscription: (show: boolean) => void;
  toggleSidebar: () => void;
  
  // Project actions
  setProject: (projectId: string | null) => void;
  setVideoBlobUrl: (url: string | null) => void;
  clearProject: () => void;
}
