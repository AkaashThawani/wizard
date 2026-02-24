/**
 * ChatInterface.tsx
 * 
 * Chat interface component for conversational AI interaction
 * with the Wizard video editing system.
 * 
 * Features:
 * - Real-time chat messages via WebSocket
 * - Message history display
 * - Typing indicators
 * - Auto-scroll to latest message
 * - Connection status indicator
 */

import { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import './ChatInterface.css';

interface ChatInterfaceProps {
  projectId: string | null;
}

export const ChatInterface = ({ projectId }: ChatInterfaceProps) => {
  const { connected, status, messages, sendMessage } = useWebSocket(projectId || undefined);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || !connected || !projectId) {
      return;
    }

    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatTimestamp = (timestamp: number | null) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Suggested action prompts
  const suggestedActions = [
    { icon: '🔍', text: 'Find mentions of...', prompt: 'find mentions of ' },
    { icon: '✂️', text: 'Trim segment', prompt: 'trim the first segment, remove 2 seconds from start' },
    { icon: '🎨', text: 'Add effect', prompt: 'add a fade in effect to segment 1' },
    { icon: '📥', text: 'Export video', prompt: 'export the final video as preview' },
  ];

  const handleSuggestedAction = (prompt: string) => {
    setInput(prompt);
  };

  return (
    <div className="chat-interface">
      {/* Header */}
      <div className="chat-header">
        <h3>🧙‍♂️ Wizard Chat</h3>
        <div className="connection-status">
          {connected ? (
            <span className="status-connected">● Connected</span>
          ) : (
            <span className="status-disconnected">○ Disconnected</span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p>👋 Hi! I'm Wizard.</p>
            <p>I can perform Magic!!</p>
          </div>
        ) : (
          messages.map((msg, index) => (
            <div
              key={index}
              className={`chat-message ${msg.role} ${msg.error ? 'error' : ''}`}
            >
              <div className="message-header">
                <span className="message-role">
                  {msg.role === 'user' ? '👤 You' : '🧙‍♂️ Wizard'}
                </span>
                {msg.timestamp && (
                  <span className="message-time">
                    {formatTimestamp(msg.timestamp)}
                  </span>
                )}
              </div>
              <div className="message-content">{msg.content}</div>
              {/* {msg.results && msg.results.length > 0 && (
                <div className="message-results">
                  <details>
                    <summary>View Details ({msg.results.length} items)</summary>
                    <pre>{JSON.stringify(msg.results, null, 2)}</pre>
                  </details>
                </div>
              )} */}
            </div>
          ))
        )}

        {/* Thinking indicator */}
        {status === 'thinking' && (
          <div className="chat-message assistant thinking">
            <div className="message-header">
              <span className="message-role">🧙‍♂️ Wizard</span>
            </div>
            <div className="message-content">
              <span className="thinking-dots">●●●</span> Thinking...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder={
            !projectId
              ? 'Upload a video to start chatting...'
              : !connected
              ? 'Connecting...'
              : 'Ask Wizard to edit your video...'
          }
          disabled={!connected || !projectId || status === 'thinking'}
          rows={2}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || !connected || !projectId || status === 'thinking'}
          className="send-button"
        >
          {status === 'thinking' ? '⏳' : 'Send'} 
        </button>
      </div>
    </div>
  );
};
