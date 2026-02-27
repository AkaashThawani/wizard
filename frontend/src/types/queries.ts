import type { SSEEvent } from './api';

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

export interface UseProjectMutationOptions {
  onSuccess?: (projectId: string) => void;
  onError?: (error: Error) => void;
}

export interface UseUploadVideoOptions {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}
