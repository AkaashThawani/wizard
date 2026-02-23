/**
 * useWebSocket.ts
 * 
 * Custom hook for managing Socket.IO WebSocket connections
 * to the Wizard chat server.
 * 
 * Features:
 * - Auto-connect/disconnect on mount/unmount
 * - Project room management
 * - Message sending and receiving
 * - Connection status tracking
 * - Automatic reconnection
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

const SOCKET_URL = 'http://localhost:5000';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number | null;
  project_id: string;
  results?: any[];
  error?: boolean;
}

export interface ChatStatus {
  status: 'idle' | 'thinking' | 'error';
  project_id: string;
}

interface UseWebSocketReturn {
  socket: Socket | null;
  connected: boolean;
  status: 'idle' | 'thinking' | 'error';
  messages: ChatMessage[];
  sendMessage: (message: string) => void;
  joinProject: (projectId: string) => void;
  leaveProject: (projectId: string) => void;
  clearMessages: () => void;
}

export const useWebSocket = (projectId?: string): UseWebSocketReturn => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<'idle' | 'thinking' | 'error'>('idle');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const currentProjectRef = useRef<string | null>(null);
  const historyLoadedRef = useRef<Set<string>>(new Set());

  // Initialize socket connection
  useEffect(() => {
    console.log('[WebSocket] Initializing connection to', SOCKET_URL);
    
    const newSocket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
    });

    // Connection event handlers
    newSocket.on('connect', () => {
      console.log('[WebSocket] Connected:', newSocket.id);
      setConnected(true);
      
      // Auto-join project if provided
      if (projectId) {
        console.log('[WebSocket] Auto-joining project:', projectId);
        newSocket.emit('join_project', { project_id: projectId });
        currentProjectRef.current = projectId;
      }
    });

    newSocket.on('disconnect', () => {
      console.log('[WebSocket] Disconnected');
      setConnected(false);
      setStatus('idle');
    });

    newSocket.on('connected', (data) => {
      console.log('[WebSocket] Server confirmed connection:', data);
    });

    // Project room handlers
    newSocket.on('joined_project', (data) => {
      console.log('[WebSocket] Joined project:', data.project_id);
      currentProjectRef.current = data.project_id;
    });

    newSocket.on('left_project', (data) => {
      console.log('[WebSocket] Left project:', data.project_id);
      if (currentProjectRef.current === data.project_id) {
        currentProjectRef.current = null;
      }
    });

    // Chat message handler
    newSocket.on('chat_message', (data: ChatMessage) => {
      console.log('[WebSocket] Received chat message:', data);
      setMessages((prev) => [...prev, data]);
    });

    // Chat status handler
    newSocket.on('chat_status', (data: ChatStatus) => {
      console.log('[WebSocket] Status update:', data.status);
      setStatus(data.status);
    });

    // Error handler
    newSocket.on('error', (data) => {
      console.error('[WebSocket] Error:', data);
      setStatus('error');
    });

    setSocket(newSocket);

    // Cleanup on unmount
    return () => {
      console.log('[WebSocket] Cleaning up connection');
      if (currentProjectRef.current) {
        newSocket.emit('leave_project', { project_id: currentProjectRef.current });
      }
      newSocket.disconnect();
    };
  }, []); // Only run once on mount

  // Load conversation history from server
  const loadConversationHistory = useCallback(async (projectId: string) => {
    try {
      console.log('[WebSocket] Loading conversation history for:', projectId);
      const response = await fetch(`http://localhost:5000/project/${projectId}/chat/history`);
      
      if (!response.ok) {
        console.warn('[WebSocket] Failed to load history:', response.statusText);
        return;
      }
      
      const data = await response.json();
      console.log('[WebSocket] Loaded', data.count, 'historical messages');
      
      // Convert history entries to chat messages
      const historicalMessages: ChatMessage[] = data.messages.map((msg: {prompt: string; summary: string; success: boolean; timestamp?: number}, index: number) => [
        {
          role: 'user' as const,
          content: msg.prompt,
          timestamp: msg.timestamp || Date.now() - (data.count - index) * 1000,
          project_id: projectId,
        },
        {
          role: 'assistant' as const,
          content: msg.summary,
          timestamp: msg.timestamp || Date.now() - (data.count - index) * 1000 + 500,
          project_id: projectId,
          error: !msg.success,
        }
      ]).flat();
      
      setMessages(historicalMessages);
    } catch (error) {
      console.error('[WebSocket] Error loading history:', error);
    }
  }, []);

  // Auto-join project when projectId changes
  useEffect(() => {
    if (socket && connected && projectId && projectId !== currentProjectRef.current) {
      console.log('[WebSocket] Project changed, joining:', projectId);
      
      // Leave old project if exists
      if (currentProjectRef.current) {
        socket.emit('leave_project', { project_id: currentProjectRef.current });
      }
      
      // Join new project
      socket.emit('join_project', { project_id: projectId });
      currentProjectRef.current = projectId;
      
      // Load conversation history for this project (if not already loaded)
      if (!historyLoadedRef.current.has(projectId)) {
        loadConversationHistory(projectId);
        historyLoadedRef.current.add(projectId);
      }
    } else if (!projectId && currentProjectRef.current) {
      // Project cleared - clear messages
      console.log('[WebSocket] Project cleared, clearing messages');
      setMessages([]);
      
      // Leave old project
      if (socket && connected) {
        socket.emit('leave_project', { project_id: currentProjectRef.current });
      }
      currentProjectRef.current = null;
    }
  }, [socket, connected, projectId, loadConversationHistory]);

  // Send chat message
  const sendMessage = useCallback((message: string) => {
    if (!socket || !connected) {
      console.warn('[WebSocket] Cannot send message - not connected');
      return;
    }

    if (!currentProjectRef.current) {
      console.warn('[WebSocket] Cannot send message - no project joined');
      return;
    }

    console.log('[WebSocket] Sending message:', message);
    
    socket.emit('chat_message', {
      project_id: currentProjectRef.current,
      message,
      timestamp: Date.now(),
    });
  }, [socket, connected]);

  // Join project manually
  const joinProject = useCallback((projectId: string) => {
    if (!socket || !connected) {
      console.warn('[WebSocket] Cannot join project - not connected');
      return;
    }

    console.log('[WebSocket] Manually joining project:', projectId);
    
    // Leave current project if exists
    if (currentProjectRef.current) {
      socket.emit('leave_project', { project_id: currentProjectRef.current });
    }

    socket.emit('join_project', { project_id: projectId });
    currentProjectRef.current = projectId;
  }, [socket, connected]);

  // Leave project manually
  const leaveProject = useCallback((projectId: string) => {
    if (!socket || !connected) {
      console.warn('[WebSocket] Cannot leave project - not connected');
      return;
    }

    console.log('[WebSocket] Manually leaving project:', projectId);
    socket.emit('leave_project', { project_id: projectId });
    
    if (currentProjectRef.current === projectId) {
      currentProjectRef.current = null;
    }
  }, [socket, connected]);

  // Clear messages
  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    socket,
    connected,
    status,
    messages,
    sendMessage,
    joinProject,
    leaveProject,
    clearMessages,
  };
};
