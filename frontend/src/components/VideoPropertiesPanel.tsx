import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Scissors, Sparkles, ArrowRightLeft, Video, FileVideo } from 'lucide-react';
import type { TimelineData } from '@/types/api';

interface VideoPropertiesPanelProps {
  timeline: TimelineData | undefined;
  showFullTranscription: boolean;
  onToggleFull: (checked: boolean) => void;
  onSegmentClick: (segmentId: string) => void;
  videoDuration: number;
}

export function VideoPropertiesPanel({ 
  timeline, 
  showFullTranscription, 
  onToggleFull, 
  onSegmentClick,
  videoDuration 
}: VideoPropertiesPanelProps) {
  // Calculate video stats
  const totalSegments = timeline?.current_sequence?.length || 0;
  const editedDuration = timeline?.current_sequence?.reduce((sum, seg) => sum + seg.duration, 0) || 0;
  
  return (
    <div className="flex h-full flex-col bg-[#141414] overflow-hidden">
      {/* Video Info Section */}
      <details className="border-b border-[#2e2e2e]" open>
        <summary className="cursor-pointer bg-[#1c1c1c] px-4 py-3 text-xs font-semibold uppercase text-[#a0a0a0] transition-colors hover:bg-[#242424] hover:text-[#4a9eff]">
          🎬 Video Info
        </summary>
        
        <div className="p-4 bg-[#141414]">
          {timeline?.source ? (
            <Card className="border-[#2e2e2e] bg-[#1c1c1c] p-4">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                <div className="col-span-2 flex items-center gap-2 pb-2 border-b border-[#2e2e2e] mb-2">
                  <FileVideo className="h-4 w-4 text-[#4a9eff]" />
                  <span className="font-semibold text-[#e8e8e8]">Video Information</span>
                </div>
                
                <div className="text-[#a0a0a0]">Filename:</div>
                <div className="text-[#e8e8e8] font-mono truncate text-right ">{timeline.source.filename}</div>
                
                <div className="text-[#a0a0a0]">Original Duration:</div>
                <div className="text-[#e8e8e8] font-mono text-right">
                  {videoDuration > 0 ? `${videoDuration.toFixed(2)}s` : 'Loading...'}
                </div>
                
                <div className="text-[#a0a0a0]">Edited Duration:</div>
                <div className="text-[#e8e8e8] font-mono text-right">{editedDuration.toFixed(2)}s</div>
                
                <div className="text-[#a0a0a0]">Total Segments:</div>
                <div className="text-right">
                  <Badge variant="secondary" className="bg-[#242424] text-[#4a9eff]">
                    {totalSegments}
                  </Badge>
                </div>
                
                <div className="text-[#a0a0a0]">Transcribed:</div>
                <div className="text-right">
                  <Badge variant="secondary" className="bg-[#242424] text-[#4a9eff]">
                    {timeline?.transcription?.length || 0}
                  </Badge>
                </div>
              </div>
            </Card>
          ) : (
            <div className="flex flex-col items-center justify-center gap-2 py-8 text-center text-sm text-[#606060]">
              <Video className="h-8 w-8 opacity-30" />
              <p>No video loaded</p>
            </div>
          )}
        </div>
      </details>
      
      {/* Edit Effects Section - Always Visible */}
      <details className="border-b border-[#2e2e2e]" open>
        <summary className="cursor-pointer bg-[#1c1c1c] px-4 py-3 text-xs font-semibold uppercase text-[#a0a0a0] transition-colors hover:bg-[#242424] hover:text-[#4a9eff]">
          ✂️ Edit Effects
        </summary>
        
        <ScrollArea className="h-[200px]">
          <div className="space-y-2 p-3">
            {(() => {
              // Compute segments with effects/transitions
              const segmentsWithEffects = timeline?.current_sequence?.filter(seg => {
                const hasTransition = !!seg.transition_in;
                const editData = timeline.layers?.edit_decisions?.[seg.id];
                const hasTrim = editData?.trim && (editData.trim.start || editData.trim.end);
                const hasEditEffects = editData?.effects && editData.effects.length > 0;
                const hasSegmentEffects = seg.effects && seg.effects.length > 0;
                const hasLayerEdits = hasTrim || hasEditEffects || hasSegmentEffects;
                return hasTransition || hasLayerEdits;
              }) || [];
              
              // Show segments if any exist
              if (segmentsWithEffects.length > 0) {
                return segmentsWithEffects.map(segment => {
                  // Merge effects from both segment itself and edit_decisions
                  const editData = timeline?.layers?.edit_decisions?.[segment.id] || {};
                  const allEffects = [
                    ...(segment.effects || []),
                    ...(editData.effects || [])
                  ];
                  return (
                    <Card
                      key={segment.id}
                      className="border-[#2e2e2e] bg-[#1c1c1c] p-3 transition-all hover:border-[#4a9eff] hover:shadow-md cursor-pointer"
                      onClick={() => onSegmentClick(segment.id)}
                    >
                      <div className="mb-2 flex items-center justify-between border-b border-[#2e2e2e] pb-2">
                        <strong className="text-xs text-[#e8e8e8]">
                          Segment {segment.id.substring(0, 8)}
                        </strong>
                        <span className="font-mono text-[10px] text-[#606060]">
                          {Math.floor(segment.start)}s - {Math.floor(segment.end)}s
                        </span>
                      </div>
                      
                      <div className="space-y-1.5">
                        {editData.trim && (
                          <div className="flex items-center gap-2 text-xs text-[#a0a0a0]">
                            <Scissors className="h-3 w-3 text-[#4a9eff]" />
                            <span>Trim: -{editData.trim.start || 0}s start, -{editData.trim.end || 0}s end</span>
                          </div>
                        )}
                        
                        {segment.transition_in && (
                          <div className="flex items-center gap-2 text-xs text-[#a0a0a0]">
                            <ArrowRightLeft className="h-3 w-3 text-[#4a9eff]" />
                            <span>
                              Transition: {segment.transition_in.type}
                              <Badge variant="secondary" className="ml-2 bg-[#242424] text-[10px]">
                                {segment.transition_in.duration_s}s
                              </Badge>
                            </span>
                          </div>
                        )}
                        
                        {allEffects.length > 0 && (
                          <div className="flex items-center gap-2 text-xs text-[#a0a0a0]">
                            <Sparkles className="h-3 w-3 text-[#4a9eff]" />
                            <span>
                              Effects: {allEffects.map((e: {type: string}) => e.type).join(', ')}
                            </span>
                          </div>
                        )}
                      </div>
                    </Card>
                  );
                });
              }
              
              // Show empty state
              if (timeline) {
                return (
                  <div className="flex flex-col items-center justify-center gap-2 py-8 text-center text-sm text-[#606060]">
                    <Sparkles className="h-8 w-8 opacity-30" />
                    <p>No effects or transitions applied</p>
                    <p className="text-xs text-[#4a4a4a]">Chat with Wizard to add effects!</p>
                  </div>
                );
              }
              
              // No timeline loaded
              return (
                <div className="flex flex-col items-center justify-center gap-2 py-8 text-center text-sm text-[#606060]">
                  <Sparkles className="h-8 w-8 opacity-30" />
                  <p>No video loaded</p>
                </div>
              );
            })()}
          </div>
        </ScrollArea>
      </details>
      
      {/* Transcription Section */}
      <details className="border-b border-[#2e2e2e] flex-1 flex flex-col overflow-hidden" open>
        <summary className="cursor-pointer bg-[#1c1c1c] px-4 py-3 text-xs font-semibold uppercase text-[#a0a0a0] transition-colors hover:bg-[#242424] hover:text-[#4a9eff]">
          📝 Transcription
        </summary>
        
        <div className="border-b border-[#333] p-4">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="full-transcription"
              checked={showFullTranscription}
              onCheckedChange={onToggleFull}
              className="rounded"
            />
            <Label
              htmlFor="full-transcription"
              className="text-xs text-[#a0a0a0] cursor-pointer hover:text-[#e8e8e8] transition-colors"
            >
              Show Full Transcription
            </Label>
          </div>
        </div>
        
        <ScrollArea className="flex-1">
          <div className="space-y-3 p-4">
            {(showFullTranscription ? timeline?.transcription : timeline?.current_sequence)
              ?.filter(seg => seg.text && seg.text.trim().length > 0)
              .sort((a, b) => a.start - b.start)
              .map((seg) => (
                <Card
                  key={seg.id}
                  className="cursor-pointer border-[#2e2e2e] bg-[#1c1c1c] p-3 transition-all hover:border-[#4a9eff] hover:bg-[#242424] hover:shadow-lg hover:scale-[1.01]"
                  onClick={() => onSegmentClick(seg.id)}
                >
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded-full bg-[#4a9eff]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#4a9eff]">
                      {Math.floor(seg.start/60)}:{(seg.start%60).toFixed(1)}
                    </span>
                    <span className="text-[#606060]">→</span>
                    <span className="rounded-full bg-[#4a9eff]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#4a9eff]">
                      {Math.floor(seg.end/60)}:{(seg.end%60).toFixed(1)}
                    </span>
                  </div>
                  <div className="text-xs leading-relaxed text-[#e8e8e8]">{seg.text}</div>
                </Card>
              ))}
          </div>
        </ScrollArea>
      </details>
    </div>
  );
}
