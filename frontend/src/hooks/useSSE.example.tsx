/**
 * Example usage of useSSE hook with auto-reconnection
 * 
 * This shows how to integrate SSE events into a React component
 * with automatic reconnection and checkpoint tracking.
 */

import { useState } from 'react';
import { useSSE, type SSEEvent } from './useSSE';

interface ProjectViewProps {
  projectId: string;
}

export function ProjectView({ projectId }: ProjectViewProps) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Use SSE hook with auto-reconnection
  const { connectionState, lastCheckpoint, reconnect } = useSSE({
    projectId,
    
    // Handle incoming events
    onEvent: (event) => {
      console.log('[SSE Event]', event);
      
      // Add to events list
      setEvents(prev => [...prev, event]);
      
      // Handle specific event types
      switch (event.event) {
        case 'transcription_start':
          console.log('Transcription started...');
          break;
          
        case 'transcription_done':
          console.log('Transcription complete:', event.data);
          break;
          
        case 'analysis_start':
          console.log('Analysis started...');
          break;
          
        case 'analysis_done':
          console.log('Analysis complete:', event.data);
          break;
          
        case 'prompt_start':
          console.log('Processing prompt:', event.data);
          break;
          
        case 'prompt_done':
          console.log('Prompt complete:', event.data);
          break;
          
        case 'error':
          console.error('Error event:', event.data);
          setError(event.data.error as string);
          break;
          
        case 'heartbeat':
          // Ignore heartbeat events (just keep-alive)
          break;
          
        default:
          console.log('Unknown event:', event.event, event.data);
      }
    },
    
    // Handle connection errors
    onError: (error) => {
      console.error('[SSE Error]', error);
      setError('Connection error - will retry automatically');
    },
    
    // Optional: Configure reconnection behavior
    reconnectDelay: 1000,  // Start with 1s delay
    maxReconnectAttempts: 10,  // Try up to 10 times
  });

  return (
    <div>
      {/* Connection Status Indicator */}
      <div className="connection-status">
        <span className={`status-dot ${connectionState}`} />
        <span>
          {connectionState === 'connected' && 'Connected'}
          {connectionState === 'connecting' && 'Connecting...'}
          {connectionState === 'disconnected' && 'Disconnected'}
          {connectionState === 'error' && 'Connection Error'}
        </span>
        
        {connectionState === 'error' && (
          <button onClick={reconnect}>Reconnect</button>
        )}
        
        {lastCheckpoint && (
          <span className="checkpoint">
            Checkpoint: {lastCheckpoint.slice(0, 8)}...
          </span>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Event Log */}
      <div className="event-log">
        <h3>Events ({events.length})</h3>
        <ul>
          {events.map((event, index) => (
            <li key={index}>
              <strong>{event.event}</strong>: {JSON.stringify(event.data)}
              {event.checkpoint_id && (
                <span className="checkpoint-id">
                  (checkpoint: {event.checkpoint_id})
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/**
 * Alternative: Minimal usage
 */
export function MinimalExample({ projectId }: ProjectViewProps) {
  const [status, setStatus] = useState<string>('');

  useSSE({
    projectId,
    onEvent: (event) => {
      setStatus(`Last event: ${event.event}`);
    },
  });

  return <div>Status: {status}</div>;
}
