import type { Project, TimelineData, PromptResponse, UploadResponse } from '../types/api';

const API_BASE = '';  // Vite proxy handles /project routes

export const api = {
  async createProject(): Promise<Project> {
    const res = await fetch('/project', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
  },

  async uploadVideo(projectId: string, file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`/project/${projectId}/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to upload video');
    return res.json();
  },

  async sendPrompt(projectId: string, prompt: string): Promise<PromptResponse> {
    const res = await fetch(`/project/${projectId}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) throw new Error('Failed to send prompt');
    return res.json();
  },

  async getTimeline(projectId: string): Promise<TimelineData> {
    const res = await fetch(`/project/${projectId}/timeline`);
    if (!res.ok) throw new Error('Failed to get timeline');
    return res.json();
  },

  createSSE(projectId: string): EventSource {
    return new EventSource(`/project/${projectId}/stream`);
  },

  async rollback(projectId: string, snapId: string): Promise<{success: boolean}> {
    const res = await fetch(`/project/${projectId}/rollback/${snapId}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to rollback');
    return res.json();
  },

  async exportTimeline(
    projectId: string,
    resolution: 'preview' | 'full' = 'preview',
    outputName: string = 'export'
  ): Promise<{output_path: string, file_size_mb: number, segment_count: number}> {
    const res = await fetch(`/project/${projectId}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        prompt: `export timeline at ${resolution} resolution as ${outputName}`
      }),
    });
    if (!res.ok) throw new Error('Failed to export');
    return res.json();
  },
};
