import { useEffect, useRef, useState, useCallback } from 'react';

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
  checkpoint_id?: string;
}

export interface UseSSEOptions {
  projectId: string;
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Event) => void;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

/**
 * Custom hook for SSE with auto-reconnection and checkpoint support.
 * 
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Checkpoint tracking for event replay
 * - Connection state management
 * - Cleanup on unmount
 */
export function useSSE({
  projectId,
  onEvent,
  onError,
  reconnectDelay = 1000,
  maxReconnectAttempts = 10,
}: UseSSEOptions) {
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [lastCheckpoint, setLastCheckpoint] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);
  
  // Store callbacks in refs to avoid recreating connect on every render
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);
  
  // Update refs when callbacks change
  useEffect(() => {
    onEventRef.current = onEvent;
    onErrorRef.current = onError;
  }, [onEvent, onError]);
  
  // Use ref to avoid circular dependency in useCallback
  const connectRef = useRef<() => void>();

  const connect = useCallback(() => {
    if (!isMountedRef.current) return;
    
    // Guard: Don't connect if projectId is invalid
    if (!projectId || projectId === 'none' || projectId === '') {
      console.log('[SSE] Skipping connection - no valid project ID');
      setConnectionState('disconnected');
      return;
    }
    
    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setConnectionState('connecting');

    // Build SSE URL with checkpoint parameter for reconnection
    let url = `/project/${projectId}/stream`;
    if (lastCheckpoint) {
      url += `?since=${encodeURIComponent(lastCheckpoint)}`;
    }

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    // Connection opened
    eventSource.onopen = () => {
      if (!isMountedRef.current) return;
      console.log(`[SSE] Connected to project ${projectId}`);
      setConnectionState('connected');
      reconnectAttemptsRef.current = 0; // Reset reconnect counter
    };

    // Message received
    eventSource.onmessage = (e) => {
      if (!isMountedRef.current) return;
      
      try {
        const event: SSEEvent = JSON.parse(e.data);
        
        // Update last checkpoint if provided
        if (event.checkpoint_id) {
          setLastCheckpoint(event.checkpoint_id);
        }

        // Call event handler using ref
        if (onEventRef.current) {
          onEventRef.current(event);
        }
      } catch (error) {
        console.error('[SSE] Failed to parse event:', error, e.data);
      }
    };

    // Connection error or closed
    eventSource.onerror = (error) => {
      if (!isMountedRef.current) return;
      
      console.warn('[SSE] Connection error:', error);
      setConnectionState('error');
      
      // Close the connection
      eventSource.close();
      eventSourceRef.current = null;

      // Call error handler using ref
      if (onErrorRef.current) {
        onErrorRef.current(error);
      }

      // Attempt reconnection with exponential backoff
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectAttemptsRef.current++;
        const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current - 1);
        
        console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`);
        
        reconnectTimeoutRef.current = window.setTimeout(() => {
          if (isMountedRef.current && connectRef.current) {
            connectRef.current();
          }
        }, delay);
      } else {
        console.error('[SSE] Max reconnection attempts reached');
        setConnectionState('disconnected');
      }
    };
  }, [projectId, lastCheckpoint, reconnectDelay, maxReconnectAttempts]); // Removed onEvent/onError - using refs

  const disconnect = useCallback(() => {
    console.log(`[SSE] Disconnecting from project ${projectId}`);
    
    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setConnectionState('disconnected');
  }, [projectId]);

  const reconnect = useCallback(() => {
    console.log(`[SSE] Manual reconnect requested for project ${projectId}`);
    reconnectAttemptsRef.current = 0; // Reset counter on manual reconnect
    disconnect();
    connect();
  }, [projectId, connect, disconnect]);

  // Store connect function in ref (in effect to avoid render-time ref update)
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Auto-connect on mount and when projectId changes
  useEffect(() => {
    isMountedRef.current = true;
    
    // Only connect if we have a valid projectId
    if (projectId && projectId !== 'none' && projectId !== '') {
      connect();
    }

    // Cleanup on unmount
    return () => {
      isMountedRef.current = false;
      
      // Clean up reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Close connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [projectId]); // Only depend on projectId, not connect/disconnect

  return {
    connectionState,
    lastCheckpoint,
    reconnect,
    disconnect,
  };
}
