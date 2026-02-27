import type { RefObject } from 'react';
import type { TimelineData } from '@/types/api';

interface VideoPlayerProps {
  timeline: TimelineData | undefined;
  videoRef: RefObject<HTMLVideoElement>;
  video2Ref: RefObject<HTMLVideoElement>;
  onPlay: () => void;
  onPause: () => void;
  onTimeUpdate: (e: React.SyntheticEvent<HTMLVideoElement>) => void;
}

export function VideoPlayer({ 
  timeline, 
  videoRef, 
  video2Ref,
  onPlay,
  onPause,
  onTimeUpdate
}: VideoPlayerProps) {
  return (
    <div className="flex flex-col items-center justify-center bg-[#0d0d0d] p-4" style={{ height: 'calc(100% - 120px)' }}>
      {timeline?.source ? (
        <div className="relative flex h-full w-full items-center justify-center">
          <video 
            ref={videoRef} 
            className="max-h-full max-w-full rounded shadow-2xl"
            onPlay={onPlay}
            onPause={onPause}
            onTimeUpdate={onTimeUpdate}
          />
          <video ref={video2Ref} className="absolute hidden" />
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="text-6xl opacity-20">🎬</div>
          <div className="text-sm text-[#606060]">Upload a video to begin editing</div>
        </div>
      )}
    </div>
  );
}
