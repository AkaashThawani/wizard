import { useState, useEffect, useRef } from 'react';
import { api } from './api/client';
import type { TimelineData } from './types/api';
import './App.css';

function App() {
  const [projectId, setProjectId] = useState<string | null>(
    localStorage.getItem('wizard_project_id')
  );
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [progress, setProgress] = useState('Ready');
  const [isLoading, setIsLoading] = useState(false);
  const [videoBlobUrl, setVideoBlobUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [virtualTime, setVirtualTime] = useState(0);
  const [totalVirtualDuration, setTotalVirtualDuration] = useState(0);
  const [currentSourceTime, setCurrentSourceTime] = useState(0);
  const [isExporting, setIsExporting] = useState(false);
  const [pendingExportDownload, setPendingExportDownload] = useState<string | null>(null);
  const [currentVideoIndex, setCurrentVideoIndex] = useState(0); // 0 or 1 for double buffer
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const video2Ref = useRef<HTMLVideoElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  // Load timeline
  const loadTimeline = async () => {
    if (!projectId) return;
    try {
      const data = await api.getTimeline(projectId);
      setTimeline(data);
    } catch (err) {
      console.error('Failed to load timeline:', err);
      // Clear stale project on error
      localStorage.removeItem('wizard_project_id');
      setProjectId(null);
      setTimeline(null);
    }
  };

  // SSE connection
  useEffect(() => {
    if (!projectId) return;

    const sse = api.createSSE(projectId);
    
    sse.onmessage = (event) => {
      try {
        const { event: eventName, data } = JSON.parse(event.data);
        if (eventName === 'prompt_done') {
          loadTimeline();
          
          // Handle export failures
          if (pendingExportDownload && !data.success) {
            setResponse(`Export failed: ${data.error || 'Unknown error'}`);
            setProgress('Failed');
            setIsExporting(false);
            setPendingExportDownload(null);
          } else {
            setProgress('Done');
          }
        } else if (eventName === 'stage') {
          setProgress(`${data.stage}: ${data.status}`);
          
          // Refresh timeline when vectorization completes
          if (data.stage === 'vectorize' && data.status === 'done') {
            loadTimeline();
            setProgress('Done');
          }
          
          // Trigger download when export completes
          if (data.stage === 'encode' && data.status === 'done' && pendingExportDownload) {
            const downloadExport = async () => {
              try {
                setProgress('Downloading...');
                const downloadUrl = `/project/${projectId}/export/export_preview.mp4`;
                const response = await fetch(downloadUrl);
                
                if (!response.ok) {
                  throw new Error(`Download failed: ${response.statusText}`);
                }
                
                const blob = await response.blob();
                const blobUrl = URL.createObjectURL(blob);
                
                // Create download link
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = `wizard_export_${new Date().getTime()}.mp4`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                
                // Clean up
                URL.revokeObjectURL(blobUrl);
                
                setProgress('Done');
                setResponse(`Export downloaded: ${data.file_size_mb || '?'} MB`);
              } catch (err) {
                setResponse(`Download error: ${err}`);
                setProgress('Failed');
              } finally {
                setPendingExportDownload(null);
                setIsExporting(false);
              }
            };
            downloadExport();
          }
        }
      } catch (e) {
        // Ignore
      }
    };

    return () => sse.close();
  }, [projectId, pendingExportDownload]);

  // Initial load
  useEffect(() => {
    if (projectId) loadTimeline();
  }, [projectId]);

  // Update video src when timeline loads (both videos)
  useEffect(() => {
    let videoSrc = '';
    
    if (videoBlobUrl) {
      // Priority 1: Use blob URL from upload (fast, no network request)
      videoSrc = videoBlobUrl;
    } else if (projectId && timeline?.source) {
      // Priority 2: Use backend HTTP endpoint (works after page refresh)
      videoSrc = `/project/${projectId}/video`;
    }
    
    // Only update if source actually changed (prevents redundant loads)
    if (videoRef.current && videoSrc && videoRef.current.src !== videoSrc) {
      videoRef.current.src = videoSrc;
      videoRef.current.muted = false;
      videoRef.current.volume = 1.0;
    }
    
    if (video2Ref.current && videoSrc && video2Ref.current.src !== videoSrc) {
      video2Ref.current.src = videoSrc;
      video2Ref.current.muted = false;
      video2Ref.current.volume = 1.0;
    }
  }, [timeline, projectId, videoBlobUrl]);

  const handleNewProject = async () => {
    try {
      const project = await api.createProject();
      setProjectId(project.project_id);
      localStorage.setItem('wizard_project_id', project.project_id);
      setTimeline(null);
      setResponse(`Created project: ${project.project_id}`);
    } catch (err) {
      setResponse(`Error: ${err}`);
    }
  };

  const handleClearProject = () => {
    localStorage.removeItem('wizard_project_id');
    setProjectId(null);
    setTimeline(null);
    setResponse('');
    setPrompt('');
    setProgress('Ready');
    if (videoRef.current) {
      videoRef.current.src = '';
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    let currentProjectId = projectId;
    
    if (!currentProjectId) {
      const project = await api.createProject();
      currentProjectId = project.project_id;
      setProjectId(currentProjectId);
      localStorage.setItem('wizard_project_id', currentProjectId);
    }

    try {
      setProgress('Uploading...');
      await api.uploadVideo(currentProjectId, file);
      
      // Store blob URL to preserve video after timeline updates
      const blobUrl = URL.createObjectURL(file);
      setVideoBlobUrl(blobUrl);
      
      if (videoRef.current) {
        videoRef.current.src = blobUrl;
        videoRef.current.muted = false;
        videoRef.current.volume = 1.0;
      }
      
      setResponse(`Uploaded: ${file.name} - Auto-transcribing in background...`);
      setProgress('Transcribing...');
      // SSE will automatically refresh when vectorize completes
    } catch (err) {
      setResponse(`Upload error: ${err}`);
      setProgress('Failed');
    }
  };

  const handleSendPrompt = async () => {
    if (!projectId || !prompt.trim() || isLoading) return;

    setIsLoading(true);
    setProgress('Processing...');

    try {
      const result = await api.sendPrompt(projectId, prompt);
      const displayText = result.full_text || result.summary;
      setResponse(displayText);
      setPrompt('');  // Clear input
      await loadTimeline();
      setProgress('Done');
    } catch (err) {
      setResponse(`Error: ${err}`);
      setProgress('Failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Calculate total virtual duration from current_sequence
  useEffect(() => {
    if (timeline?.current_sequence) {
      const total = timeline.current_sequence.reduce((sum, seg) => sum + seg.duration, 0);
      setTotalVirtualDuration(total);
      
      // 🔍 DEBUG: Log segment layout
      console.log('📊 Segment Layout:', timeline.current_sequence.map((seg, idx) => {
        const cumulativeDuration = timeline.current_sequence
          .slice(0, idx + 1)
          .reduce((sum, s) => sum + s.duration, 0);
        return {
          index: idx,
          duration: seg.duration.toFixed(2) + 's',
          flexGrow: seg.duration,
          cumulativeEnd: cumulativeDuration.toFixed(2) + 's',
          expectedEndPercentage: ((cumulativeDuration / total) * 100).toFixed(2) + '%'
        };
      }));
      
      console.log(`📏 Total Duration: ${total.toFixed(2)}s across ${timeline.current_sequence.length} segments`);
    }
  }, [timeline]);

  // Convert virtual time to source time
  const virtualToSource = (vTime: number): number => {
    if (!timeline?.current_sequence) return 0;
    
    let accumulated = 0;
    for (const seg of timeline.current_sequence) {
      if (vTime < accumulated + seg.duration) {
        return seg.start + (vTime - accumulated);
      }
      accumulated += seg.duration;
    }
    return timeline.current_sequence[timeline.current_sequence.length - 1]?.end || 0;
  };

  // Convert source time to virtual time
  const sourceToVirtual = (sTime: number): number => {
    if (!timeline?.current_sequence || timeline.current_sequence.length === 0) return 0;
    
    // Before first segment - stay at 0
    if (sTime < timeline.current_sequence[0].start) {
      return 0;
    }
    
    // After last segment - stay at total duration
    const lastSeg = timeline.current_sequence[timeline.current_sequence.length - 1];
    if (sTime > lastSeg.end) {
      return totalVirtualDuration;
    }
    
    let accumulated = 0;
    let lastSegmentEnd = 0;
    
    for (const seg of timeline.current_sequence) {
      if (sTime >= seg.start && sTime <= seg.end) {
        return accumulated + (sTime - seg.start);
      }
      
      // If we're between this segment and the next, stay at previous segment's end
      if (sTime < seg.start && lastSegmentEnd > 0) {
        return lastSegmentEnd;
      }
      
      accumulated += seg.duration;
      lastSegmentEnd = accumulated;
    }
    
    // Fallback: return last segment's end
    return lastSegmentEnd;
  };

  // Update virtual time as video plays
  useEffect(() => {
    if (!videoRef.current || !timeline?.current_sequence) return;
    
    const video = videoRef.current;
    const BUFFER = 0.02; // Jump 20ms before segment ends (minimal cutoff)
    
    const updateVirtualTime = () => {
      // GUARD: Check if timeline and sequence still exist
      if (!timeline?.current_sequence || timeline.current_sequence.length === 0) {
        return;
      }
      
      // Update source time state for playhead rendering
      setCurrentSourceTime(video.currentTime);
      
      const vTime = sourceToVirtual(video.currentTime);
      setVirtualTime(vTime);
      
      // Auto-detect playback mode: filtered timeline vs full transcription
      const isFilteredTimeline = timeline.current_sequence.length < timeline.transcription.length;
      
      // 🔍 DEBUG LOGGING - Calculate total fresh each time to avoid closure issues
      const currentTotal = timeline.current_sequence.reduce((sum, seg) => sum + seg.duration, 0);
      const percentage = currentTotal > 0 ? (vTime / currentTotal) * 100 : 0;
      const containerWidth = timelineRef.current?.getBoundingClientRect().width || 0;
      const playheadPixelPos = currentTotal > 0 ? (vTime / currentTotal) * containerWidth : 0;
      
      console.log('⏱️ Playback Debug:', {
        mode: isFilteredTimeline ? 'SEQUENCE' : 'FULL',
        sourceTime: `${video.currentTime.toFixed(2)}s / ${video.duration.toFixed(2)}s`,
        sourcePercentage: `${((video.currentTime / video.duration) * 100).toFixed(2)}%`,
        virtualTime: `${vTime.toFixed(2)}s / ${currentTotal.toFixed(2)}s`,
        virtualPercentage: `${percentage.toFixed(2)}%`,
        playheadPosition: `${playheadPixelPos.toFixed(1)}px (${percentage.toFixed(2)}%)`,
        containerWidth: `${containerWidth}px`,
        currentSegmentIndex: timeline.current_sequence.findIndex(
          seg => video.currentTime >= seg.start && video.currentTime <= seg.end
        )
      });
      
      // Only jump between segments if timeline is filtered (after search/edit)
      if (!isFilteredTimeline) {
        // Full playback mode - play entire video continuously
        return;
      }
      
      // Sequence mode - jump between selected segments
      const currentSegIndex = timeline.current_sequence.findIndex(
        seg => video.currentTime >= seg.start && video.currentTime <= seg.end
      );
      
      if (currentSegIndex >= 0) {
        const currentSeg = timeline.current_sequence[currentSegIndex];
        
        // Check if this is the last segment and we're past its end
        if (currentSegIndex === timeline.current_sequence.length - 1) {
          if (video.currentTime >= currentSeg.end - BUFFER) {
            // Last segment ending - stop playback
            video.pause();
            setIsPlaying(false);
            video.currentTime = timeline.current_sequence[0].start;
            return;
          }
        } else {
          // Not last segment - check if we should jump to next
          if (video.currentTime >= currentSeg.end - BUFFER) {
            const nextSegIndex = currentSegIndex + 1;
            video.currentTime = timeline.current_sequence[nextSegIndex].start;
          }
        }
      } else {
        // We're outside any segment, jump to next or stop
        const nextSeg = timeline.current_sequence.find(
          seg => seg.start > video.currentTime
        );
        if (nextSeg) {
          video.currentTime = nextSeg.start;
        } else {
          // Past all segments, stop
          video.pause();
          setIsPlaying(false);
          video.currentTime = timeline.current_sequence[0].start;
        }
      }
    };
    
    video.addEventListener('timeupdate', updateVirtualTime);
    video.addEventListener('play', () => setIsPlaying(true));
    video.addEventListener('pause', () => setIsPlaying(false));
    
    return () => {
      video.removeEventListener('timeupdate', updateVirtualTime);
      video.removeEventListener('play', () => setIsPlaying(true));
      video.removeEventListener('pause', () => setIsPlaying(false));
    };
  }, [timeline]);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play();
    }
  };

  const seekVirtual = (vTime: number) => {
    if (!videoRef.current) return;
    const sourceTime = virtualToSource(vTime);
    videoRef.current.currentTime = sourceTime;
    setVirtualTime(vTime);
  };

  const handleSegmentClick = (start: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = start;
      videoRef.current.play();
    }
  };

  const handleRollback = async (snapId: string) => {
    if (!projectId) return;
    try {
      await api.rollback(projectId, snapId);
      await loadTimeline();
      setResponse(`Rolled back to snapshot: ${snapId}`);
    } catch (err) {
      setResponse(`Rollback error: ${err}`);
    }
  };

  const handleExport = async () => {
    if (!projectId || isExporting) return;
    
    setIsExporting(true);
    setProgress('Exporting...');
    setPendingExportDownload(projectId); // Signal SSE to download when ready
    
    try {
      await api.exportTimeline(projectId, 'preview');
      // Download will be triggered by SSE listener when encode completes
    } catch (err) {
      setResponse(`Export error: ${err}`);
      setProgress('Failed');
      setIsExporting(false);
      setPendingExportDownload(null);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="app">
      <header className="header">
        <span className="logo">⬡ WIZARD</span>
        <span className="project-id">
          {projectId ? `project: ${projectId}` : 'No project'}
        </span>
        <div className="header-actions">
          <button onClick={handleNewProject} className="btn-secondary">
            New Project
          </button>
          {projectId && (
            <button onClick={handleClearProject} className="btn-secondary" style={{background:'#dc3545'}}>
              Clear Project
            </button>
          )}
          <label className="btn-primary">
            Upload Video
            <input type="file" accept="video/*" onChange={handleUpload} style={{display:'none'}} />
          </label>
        </div>
      </header>

      <main className="main">
        <div className="video-area">
          {timeline?.source ? (
            <div className="video-stack">
              <video 
                ref={videoRef} 
                className={`video-player ${currentVideoIndex === 0 ? 'active' : 'hidden'}`}
              />
              <video 
                ref={video2Ref} 
                className={`video-player ${currentVideoIndex === 1 ? 'active' : 'hidden'}`}
              />
            </div>
          ) : (
            <div className="placeholder">Upload a video to begin</div>
          )}
        </div>

        <div className="timeline-area">
          <div className="timeline-header">
            <button onClick={togglePlay} className="timeline-play-btn" disabled={!timeline?.source}>
              {isPlaying ? '⏸' : '▶'}
            </button>
            <span>Timeline</span>
            {timeline && timeline.current_sequence.length < timeline.transcription.length && (
              <>
                <span className="badge">{timeline.current_sequence.length} clips</span>
                <span className="time-display">
                  {formatTime(virtualTime)} / {formatTime(totalVirtualDuration)}
                </span>
              </>
            )}
            {timeline && timeline.current_sequence.length > 0 && (
              <button 
                onClick={handleExport}
                disabled={isExporting}
                className="btn-primary"
                style={{marginLeft: 'auto', fontSize: '11px', padding: '4px 10px'}}
              >
                {isExporting ? '⏳ Exporting...' : '📥 Export'}
              </button>
            )}
          </div>
          {timeline?.current_sequence && timeline.current_sequence.length > 0 && progress === 'Done' ? (
            <div className="timeline-container" ref={timelineRef}>
              {/* Hidden range input - handles all dragging logic */}
              <input
                type="range"
                min={0}
                max={totalVirtualDuration}
                step={0.01}
                value={virtualTime}
                onChange={(e) => seekVirtual(parseFloat(e.target.value))}
                className="timeline-range-hidden"
                disabled={!timeline?.source}
              />
              
              {/* Visible segments - full duration timeline */}
              <div className="timeline-scroll">
                {timeline.current_sequence.map((seg, idx) => {
                  const videoDuration = videoRef.current?.duration || 60;
                  return (
                    <div
                      key={seg.id}
                      className={`segment-block ${idx % 2 === 0 ? 'even' : 'odd'}`}
                      style={{
                        left: `${(seg.start / videoDuration) * 100}%`,
                        width: `${(seg.duration / videoDuration) * 100}%`
                      }}
                      title={`${seg.duration.toFixed(1)}s: ${seg.text}`}
                      onClick={() => handleSegmentClick(seg.start)}
                    />
                  );
                })}
              </div>
              
              {/* Custom visual playhead - positioned by source time */}
              <div 
                className="playhead-visual" 
                style={{
                  left: videoRef.current?.duration 
                    ? `${(currentSourceTime / videoRef.current.duration) * 100}%`
                    : '0%'
                }}
              >
                <div className="playhead-handle"></div>
                <div className="playhead-line"></div>
              </div>
            </div>
          ) : (
            <div className="timeline-status">
              <span>{progress}</span>
            </div>
          )}
        </div>

        <div className="sidebar">
          <div className="prompt-section">
            <h3>Prompt</h3>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. find mentions of machine learning"
              rows={4}
            />
            <button
              onClick={handleSendPrompt}
              disabled={isLoading}
              className="btn-primary"
            >
              {isLoading ? 'Processing...' : 'Send'}
            </button>
          </div>

          <details open className="panel">
            <summary>Response</summary>
            <div className="content">{response || 'No response yet'}</div>
          </details>

          <details className="panel">
            <summary>Transcription</summary>
            <div className="content transcription-list">
              {timeline?.transcription.map(seg => (
                <div
                  key={seg.id}
                  className="trans-item"
                  onClick={() => handleSegmentClick(seg.start)}
                >
                  <div className="trans-time">
                    [{Math.floor(seg.start/60)}:{(seg.start%60).toFixed(1)} - {Math.floor(seg.end/60)}:{(seg.end%60).toFixed(1)}]
                  </div>
                  <div>{seg.text}</div>
                </div>
              ))}
            </div>
          </details>

          <details className="panel">
            <summary>History</summary>
            <div className="content">
              {timeline?.history.map((h, i) => (
                <div 
                  key={i} 
                  className="history-item"
                  onClick={() => h.snapshot_ref && handleRollback(h.snapshot_ref)}
                  title="Click to rollback to this state"
                >
                  <strong>{h.prompt}</strong>
                  <div>{h.summary}</div>
                </div>
              ))}
            </div>
          </details>
        </div>
      </main>
    </div>
  );
}

export default App;
