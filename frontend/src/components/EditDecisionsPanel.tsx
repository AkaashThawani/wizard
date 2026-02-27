import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Scissors, Sparkles, ArrowRightLeft } from 'lucide-react';
import type { TimelineData } from '@/types/api';

interface EditDecisionsPanelProps {
  timeline: TimelineData | undefined;
  onSegmentClick: (segmentId: string) => void;
}

export function EditDecisionsPanel({ timeline, onSegmentClick }: EditDecisionsPanelProps) {
  if (!timeline) return null;

  const hasEditDecisions = 
    timeline.current_sequence.some(s => s.transition_in) || 
    (timeline.layers?.edit_agent && Object.keys(timeline.layers.edit_agent).length > 0);

  if (!hasEditDecisions) return null;

  return (
    <details className="border-b border-[#2e2e2e]">
      <summary className="cursor-pointer bg-[#1c1c1c] px-3 py-2.5 text-xs font-semibold uppercase text-[#a0a0a0] transition-colors hover:bg-[#242424] hover:text-[#4a9eff]">
        ✂️ Edit Decisions
      </summary>
      
      <ScrollArea className="h-[300px]">
        <div className="space-y-2 p-3">
          {timeline.current_sequence
            .filter(seg => {
              const hasTransition = !!seg.transition_in;
              const hasLayerEdits = timeline.layers?.edit_agent?.[seg.id];
              return hasTransition || hasLayerEdits;
            })
            .map(segment => {
              const editData = timeline.layers?.edit_agent?.[segment.id] || {};
              return (
                <Card
                  key={segment.id}
                  className="border-[#2e2e2e] bg-[#1c1c1c] p-3 transition-all hover:border-[#4a9eff] hover:shadow-md"
                >
                  <div 
                    className="mb-2 flex cursor-pointer items-center justify-between border-b border-[#2e2e2e] pb-2"
                    onClick={() => onSegmentClick(segment.id)}
                  >
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
                    
                    {editData.effects && editData.effects.length > 0 && (
                      <div className="flex items-center gap-2 text-xs text-[#a0a0a0]">
                        <Sparkles className="h-3 w-3 text-[#4a9eff]" />
                        <span>
                          Effects: {editData.effects.map((e: any) => e.type).join(', ')}
                        </span>
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
        </div>
      </ScrollArea>
    </details>
  );
}
