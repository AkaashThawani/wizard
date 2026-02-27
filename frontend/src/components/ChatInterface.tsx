/**
 * ChatInterface.tsx
 * 
 * Chat interface component for conversational AI interaction
 * with the Wizard video editing system using only Tailwind CSS.
 */

import { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

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

  return (
    <div className="flex h-full flex-col bg-[#141414]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2e2e2e] bg-[#1c1c1c] px-4 py-3">
        <h3 className="text-xs font-semibold uppercase text-[#e8e8e8]">🧙‍♂️ Wizard Chat</h3>
        <div className="text-xs">
          {connected ? (
            <span className="flex items-center gap-1.5 rounded-full bg-green-500/10 px-2 py-1 text-green-400">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400"></span>
              Connected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 rounded-full bg-gray-500/10 px-2 py-1 text-gray-500">
              <span className="h-1.5 w-1.5 rounded-full bg-gray-500"></span>
              Disconnected
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-[#606060]">
            <div className="text-4xl">🧙‍♂️</div>
            <p className="text-base">Hi! I'm Wizard.</p>
            <p>I can perform Magic!!</p>
          </div>
        ) : (
          messages.map((msg, index) => (
            <div
              key={index}
              className={`rounded-2xl p-3 transition-all hover:scale-[1.01] ${
                msg.role === 'user' 
                  ? 'bg-[#1c1c1c] border border-[#2e2e2e] hover:border-[#4a9eff]/30' 
                  : msg.error
                  ? 'bg-red-900/20 border border-red-500/30'
                  : 'bg-[#1a1a1a] border border-[#2e2e2e] hover:border-[#4a9eff]/30'
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="flex items-center gap-1.5 rounded-full bg-[#4a9eff]/10 px-2 py-0.5 text-xs font-medium text-[#4a9eff]">
                  {msg.role === 'user' ? '👤 You' : '🧙‍♂️ Wizard'}
                </span>
                {msg.timestamp && (
                  <span className="rounded-full bg-[#2e2e2e] px-2 py-0.5 text-[10px] text-[#606060]">
                    {formatTimestamp(msg.timestamp)}
                  </span>
                )}
              </div>
              <div className="text-sm leading-relaxed text-[#e8e8e8]">{msg.content}</div>
            </div>
          ))
        )}

        {/* Thinking indicator */}
        {status === 'thinking' && (
          <div className="rounded-2xl bg-[#1a1a1a] border border-[#2e2e2e] p-3 animate-pulse">
            <div className="mb-2 flex items-center gap-1.5 rounded-full bg-[#4a9eff]/10 px-2 py-0.5 text-xs font-medium text-[#4a9eff] w-fit">
              🧙‍♂️ Wizard
            </div>
            <div className="text-sm text-[#e8e8e8]">
              <span>●●●</span> Thinking...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-[#2e2e2e] bg-[#1c1c1c] p-4">
        <div className="flex gap-3">
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
            className="flex-1 resize-none rounded-xl bg-[#0d0d0d] border border-[#2e2e2e] px-4 py-3 text-sm text-[#e8e8e8] placeholder-[#606060] focus:border-[#4a9eff] focus:outline-none focus:ring-2 focus:ring-[#4a9eff]/20 disabled:opacity-50 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !connected || !projectId || status === 'thinking'}
            className="rounded-xl bg-[#4a9eff] px-6 text-sm font-semibold text-white transition-all hover:bg-[#3a8eef] hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 disabled:hover:bg-[#4a9eff] shadow-lg shadow-[#4a9eff]/20"
          >
            {status === 'thinking' ? '⏳' : '📤'}
          </button>
        </div>
      </div>
    </div>
  );
};
