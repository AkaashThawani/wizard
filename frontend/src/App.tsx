import { useState, useEffect, useRef } from 'react';
import { useWizardStore } from '@/store/useWizardStore';
import { useCreateProject, useUploadVideo } from '@/queries/useProjects';
import { useTimeline } from '@/queries/useTimeline';
import { api } from './api/client';
import { useSSE, type SSEEvent } from './hooks/useSSE';
import { useWebSocket } from './hooks/useWebSocket';
import { AppHeader } from './components/AppHeader';
import { VideoPlayer } from './components/VideoPlayer';
import { TimelinePanel } from './components/TimelinePanel';
import { ChatInterface } from './components/ChatInterface';
import { VideoPropertiesPanel } from './components/VideoPropertiesPanel';

function App() {
  // Zustand store
  const projectId = useWizardStore((state) => state.project.projectId);
  const videoBlobUrl = useWizardStore((state) => state.project.videoBlobUrl);
  const isPlaying = useWizardStore((state) => state.player.isPlaying);
  const { setProject, clearProject: storeClearProject, setPlaying, setCurrentTime } = useWizardStore();
  
  // TanStack Query
  const createProject = useCreateProject();
  const uploadVideo = useUploadVideo();
  const { data: timeline, refetch: refetchTimeline } = useTimeline({ projectId });
  
  // Local state
  const [progress, setProgress] = useState('Ready');
  const [virtualTime, setVirtualTime] = useState(0);
  const [totalVirtualDuration, setTotalVirtualDuration] = useState(0);
  const [videoDuration, setVideoDuration] = useState(60);
  const [isExporting, setIsExporting] = useState(false);
  const [showFullTranscription, setShowFullTranscription] = useState(false);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const video2Ref = useRef<HTMLVideoElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  
  // WebSocket for chat
  const { messages: chatMessages } = useWebSocket(projectId || undefined);
  
  // Refresh timeline when chat completes
  useEffect(() => {
    if (chatMessages.length > 0) {
      const lastMessage = chatMessages[chatMessages.length - 1];
      if (lastMessage.role === 'assistant' && !lastMessage.error) {
        refetchTimeline().then(() => setProgress('Done'));
      }
    }
  }, [chatMessages, refetchTimeline]);
  
  // SSE connection
  useSSE({
    projectId: projectId || 'none',
    onEvent: (event: SSEEvent) => {
      const { event: eventName, data } = event;
      
      if (eventName === 'prompt_done') {
        refetchTimeline();
        setProgress('Done');
      } else if (eventName === 'stage') {
        setProgress(`${data.stage}: ${data.status}`);
        if (data.stage === 'vectorize' && data.status === 'done') {
          refetchTimeline();
          setProgress('Done');
        }
      }
    },
    onError: (error) => console.error('[SSE] Error:', error),
  });
  
  // Video source management
  useEffect(() => {
    const videoSrc = videoBlobUrl || (projectId && timeline?.source ? `/project/${projectId}/video` : '');
    
    if (videoRef.current && videoSrc && videoRef.current.src !== videoSrc) {
      videoRef.current.src = videoSrc;
      videoRef.current.muted = false;
      videoRef.current.volume = 1.0;
    }
    if (video2Ref.current && videoSrc && video2Ref.current.src !== videoSrc) {
      video2Ref.current.src = videoSrc;
    }
  }, [timeline, projectId, videoBlobUrl]);
  
  // Update video duration in state
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    
    const handleLoadedMetadata = () => {
      setVideoDuration(video.duration);
    };
    
    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    return () => video.removeEventListener('loadedmetadata', handleLoadedMetadata);
  }, []);
  
  // Calculate virtual duration
  useEffect(() => {
    if (timeline?.current_sequence) {
      const total = timeline.current_sequence.reduce((sum, seg) => sum + seg.duration, 0);
      setTotalVirtualDuration(total);
    }
  }, [timeline]);
  
  // Handlers
  const handleNewProject = () => createProject.mutate();
  
  const handleClearProject = () => {
    storeClearProject();
    setProgress('Ready');
    if (videoRef.current) videoRef.current.src = '';
    if (video2Ref.current) video2Ref.current.src = '';
  };
  
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    let currentProjectId = projectId;
    if (!currentProjectId) {
      const project = await api.createProject();
      currentProjectId = project.project_id;
      setProject(currentProjectId);
    }
    
    uploadVideo.mutate({ projectId: currentProjectId, file });
    setProgress('Uploading...');
  };
  
  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play();
    }
  };
  
  const handleSegmentClick = (segmentId: string) => {
    if (!videoRef.current || !timeline) return;
    const segment = timeline.current_sequence.find(seg => seg.id === segmentId);
    if (segment) {
      videoRef.current.currentTime = segment.start;
      videoRef.current.play();
    }
  };
  
  const handleExport = async () => {
    if (!projectId || isExporting) return;
    setIsExporting(true);
    setProgress('Exporting...');
    try {
      await api.exportTimeline(projectId, 'preview');
    } catch (err) {
      console.error('Export error:', err);
      setProgress('Failed');
      setIsExporting(false);
    }
  };

  return (
    <div className="flex h-screen flex-col bg-[#0d0d0d]">
      <AppHeader
        projectId={projectId}
        onNewProject={handleNewProject}
        onClearProject={handleClearProject}
        onUpload={handleUpload}
        isCreating={createProject.isPending}
      />

      <main className="flex h-full overflow-hidden">
        <div className="flex flex-1 flex-col min-w-0">
          <VideoPlayer
            timeline={timeline}
            videoRef={videoRef}
            video2Ref={video2Ref}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onTimeUpdate={(e) => {
              const currentTime = (e.target as HTMLVideoElement).currentTime;
              setCurrentTime(currentTime);
              
              // Update virtualTime based on current segment
              if (timeline?.current_sequence) {
                let accumulatedTime = 0;
                for (const seg of timeline.current_sequence) {
                  if (currentTime >= seg.start && currentTime < seg.end) {
                    // Currently in this segment
                    const segmentProgress = currentTime - seg.start;
                    setVirtualTime(accumulatedTime + segmentProgress);
                    break;
                  }
                  accumulatedTime += seg.duration;
                }
              }
            }}
          />
          
          <TimelinePanel
            timeline={timeline}
            isPlaying={isPlaying}
            progress={progress}
            virtualTime={virtualTime}
            totalVirtualDuration={totalVirtualDuration}
            videoDuration={videoDuration}
            isExporting={isExporting}
            timelineRef={timelineRef}
            onTogglePlay={togglePlay}
            onExport={handleExport}
            onSegmentClick={handleSegmentClick}
          />
        </div>

        {/* Expanded Sidebar - Split into 2 columns */}
        <div className="flex w-[700px] border-l border-[#2e2e2e]">
          {/* Left Column: Video Properties */}
          <div className="w-[350px] border-r border-[#2e2e2e]">
            <VideoPropertiesPanel
              timeline={timeline}
              showFullTranscription={showFullTranscription}
              onToggleFull={setShowFullTranscription}
              onSegmentClick={handleSegmentClick}
              videoDuration={videoDuration}
            />
          </div>
          
          {/* Right Column: Chat */}
          <div className="w-[350px] flex flex-col bg-[#141414]">
            <ChatInterface projectId={projectId} />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
