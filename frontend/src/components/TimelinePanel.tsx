import type { RefObject } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Play, Pause, Download } from 'lucide-react';
import { formatTime } from '@/lib/utils';
import type { TimelineData } from '@/types/api';

interface TimelinePanelProps {
  timeline: TimelineData | undefined;
  isPlaying: boolean;
  progress: string;
  virtualTime: number;
  totalVirtualDuration: number;
  videoDuration: number;
  isExporting: boolean;
  timelineRef: RefObject<HTMLDivElement>;
  onTogglePlay: () => void;
  onExport: () => void;
  onSegmentClick: (segmentId: string) => void;
}

export function TimelinePanel({
  timeline,
  isPlaying,
  progress,
  virtualTime,
  totalVirtualDuration,
  videoDuration,
  isExporting,
  timelineRef,
  onTogglePlay,
  onExport,
  onSegmentClick
}: TimelinePanelProps) {
  return (
    <div className="flex h-[120px] flex-col border-t border-[#2e2e2e] bg-[#141414]">
      <div className="flex items-center gap-3 border-b border-[#2e2e2e] px-4 py-3">
        <Button
          onClick={onTogglePlay}
          disabled={!timeline?.source}
          size="icon"
          variant="outline"
          className="border-[#2e2e2e] bg-[#1c1c1c] text-[#4a9eff] hover:border-[#4a9eff] hover:bg-[#242424] disabled:opacity-30"
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        
        <div className="flex items-center gap-2 rounded-xl border border-[#2e2e2e] bg-[#1c1c1c] px-4 py-2">
          <span className="text-xs font-semibold uppercase text-[#e8e8e8]">Timeline</span>
          <span className="text-[#2e2e2e]">|</span>
          <Badge variant="secondary" className="bg-[#242424] text-[#a0a0a0]">
            {progress}
          </Badge>
          {timeline && timeline.current_sequence.length < timeline.transcription.length && (
            <>
              <span className="text-[#2e2e2e]">|</span>
              <span className="text-xs text-[#a0a0a0]">{timeline.current_sequence.length} clips</span>
              <span className="text-[#2e2e2e]">|</span>
              <span className="text-xs font-mono text-[#a0a0a0]">
                {formatTime(virtualTime)} / {formatTime(totalVirtualDuration)}
              </span>
            </>
          )}
        </div>
        
        {timeline && timeline.current_sequence.length > 0 && (
          <Button
            onClick={onExport}
            disabled={isExporting}
            size="sm"
            className="ml-auto gap-2 bg-[#4a9eff] hover:bg-[#3a8eef]"
          >
            <Download className="h-4 w-4" />
            {isExporting ? 'Exporting...' : 'Export'}
          </Button>
        )}
      </div>
      
      {timeline?.current_sequence && timeline.current_sequence.length > 0 && progress === 'Done' ? (
        <div ref={timelineRef} className="relative flex-1 overflow-hidden p-2">
          {timeline.current_sequence.map((seg, idx) => {
            // Find the max timestamp to use as baseline
            const maxEnd = Math.max(...timeline.current_sequence.map(s => s.end));
            const duration = videoDuration > maxEnd ? videoDuration : maxEnd;
            
            // Position based on original video timestamps
            const leftPercent = (seg.start / duration) * 100;
            const widthPercent = (seg.duration / duration) * 100;
            
            return (
              <div
                key={seg.id}
                className={`group absolute h-[calc(100%-16px)] cursor-pointer rounded-lg border border-[#2e2e2e] transition-all hover:scale-105 hover:border-[#4a9eff] hover:shadow-lg hover:shadow-[#4a9eff]/20 ${
                  idx % 2 === 0 ? 'bg-[#1c1c1c]' : 'bg-[#1a1a1a]'
                }`}
                style={{
                  left: `${leftPercent}%`,
                  width: `${widthPercent}%`,
                }}
                title={`Segment ${idx + 1} - ${seg.duration.toFixed(1)}s: ${seg.text}`}
                onClick={() => onSegmentClick(seg.id)}
              >
                <div className="flex h-full items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                  <span className="text-xs font-bold text-[#4a9eff]">#{idx + 1}</span>
                </div>
              </div>
            );
          })}
          
          {/* Playhead/Scrubber */}
          {totalVirtualDuration > 0 && (
            <div
              className="absolute cursor-grab top-0 bottom-0 w-1 bg-[#ff0066] z-50 transition-all duration-75 ease-linear cursor-ew-resize"
              style={{
                left: `${(virtualTime / totalVirtualDuration) * 100}%`,
                boxShadow: '0 0 10px rgba(255, 0, 102, 0.8)',
              }}
              onMouseDown={(e) => {
                e.preventDefault();
                const timelineEl = timelineRef.current;
                if (!timelineEl || !timeline?.current_sequence) return;
                
                const handleMouseMove = (moveEvent: MouseEvent) => {
                  const rect = timelineEl.getBoundingClientRect();
                  const x = moveEvent.clientX - rect.left;
                  const percent = Math.max(0, Math.min(1, x / rect.width));
                  const newVirtualTime = percent * totalVirtualDuration;
                  
                  // Find corresponding real time in sequence
                  let accumulated = 0;
                  for (const seg of timeline.current_sequence) {
                    if (newVirtualTime >= accumulated && newVirtualTime < accumulated + seg.duration) {
                      const segmentOffset = newVirtualTime - accumulated;
                      const realTime = seg.start + segmentOffset;
                      
                      const video = document.querySelector('video');
                      if (video) video.currentTime = realTime;
                      break;
                    }
                    accumulated += seg.duration;
                  }
                };
                
                const handleMouseUp = () => {
                  document.removeEventListener('mousemove', handleMouseMove);
                  document.removeEventListener('mouseup', handleMouseUp);
                };
                
                document.addEventListener('mousemove', handleMouseMove);
                document.addEventListener('mouseup', handleMouseUp);
              }}
            >
              <div 
                className="absolute -top-2 -left-2 w-5 h-5 bg-[#ff0066] rounded-full transition-transform hover:scale-125" 
                style={{
                  boxShadow: '0 0 10px rgba(255, 0, 102, 0.8)',
                }} 
              />
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center text-xs text-[#606060]">
          {progress !== 'Done' && progress !== 'Ready' && (
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#4a9eff] border-t-transparent" />
              Processing...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
