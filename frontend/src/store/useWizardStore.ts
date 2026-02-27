import { create } from 'zustand';
import type { WizardStore } from '@/types/store';

export const useWizardStore = create<WizardStore>((set) => ({
  // Initial state
  player: {
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    virtualTime: 0,
    volume: 1.0,
    muted: false,
  },
  
  ui: {
    selectedSegmentId: null,
    expandedPanels: new Set(['transcription']),
    showFullTranscription: false,
    sidebarCollapsed: false,
  },
  
  project: {
    projectId: typeof window !== 'undefined' 
      ? localStorage.getItem('wizard_project_id') 
      : null,
    videoBlobUrl: null,
  },
  
  // Player actions
  setPlaying: (playing) => 
    set((state) => ({ 
      player: { ...state.player, isPlaying: playing } 
    })),
  
  setCurrentTime: (time) => 
    set((state) => ({ 
      player: { ...state.player, currentTime: time } 
    })),
  
  setDuration: (duration) => 
    set((state) => ({ 
      player: { ...state.player, duration } 
    })),
  
  setVirtualTime: (time) => 
    set((state) => ({ 
      player: { ...state.player, virtualTime: time } 
    })),
  
  setVolume: (volume) => 
    set((state) => ({ 
      player: { ...state.player, volume } 
    })),
  
  setMuted: (muted) => 
    set((state) => ({ 
      player: { ...state.player, muted } 
    })),
  
  // UI actions
  togglePanel: (panelId) => 
    set((state) => {
      const panels = new Set(state.ui.expandedPanels);
      if (panels.has(panelId)) {
        panels.delete(panelId);
      } else {
        panels.add(panelId);
      }
      return { ui: { ...state.ui, expandedPanels: panels } };
    }),
  
  setPanelExpanded: (panelId, expanded) => 
    set((state) => {
      const panels = new Set(state.ui.expandedPanels);
      if (expanded) {
        panels.add(panelId);
      } else {
        panels.delete(panelId);
      }
      return { ui: { ...state.ui, expandedPanels: panels } };
    }),
  
  selectSegment: (segmentId) => 
    set((state) => ({ 
      ui: { ...state.ui, selectedSegmentId: segmentId } 
    })),
  
  setShowFullTranscription: (show) => 
    set((state) => ({ 
      ui: { ...state.ui, showFullTranscription: show } 
    })),
  
  toggleSidebar: () => 
    set((state) => ({ 
      ui: { ...state.ui, sidebarCollapsed: !state.ui.sidebarCollapsed } 
    })),
  
  // Project actions
  setProject: (projectId) => {
    set({ 
      project: { projectId, videoBlobUrl: null },
      player: {
        isPlaying: false,
        currentTime: 0,
        duration: 0,
        virtualTime: 0,
        volume: 1.0,
        muted: false,
      }
    });
    
    if (projectId) {
      localStorage.setItem('wizard_project_id', projectId);
    } else {
      localStorage.removeItem('wizard_project_id');
    }
  },
  
  setVideoBlobUrl: (url) => 
    set((state) => ({ 
      project: { ...state.project, videoBlobUrl: url } 
    })),
  
  clearProject: () => {
    localStorage.removeItem('wizard_project_id');
    set({ 
      project: { projectId: null, videoBlobUrl: null },
      player: {
        isPlaying: false,
        currentTime: 0,
        duration: 0,
        virtualTime: 0,
        volume: 1.0,
        muted: false,
      },
      ui: {
        selectedSegmentId: null,
        expandedPanels: new Set(['transcription']),
        showFullTranscription: false,
        sidebarCollapsed: false,
      }
    });
  },
}));
