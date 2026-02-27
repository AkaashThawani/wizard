import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Card } from '@/components/ui/card';
import type { TimelineData } from '@/types/api';

interface TranscriptionPanelProps {
  timeline: TimelineData | undefined;
  showFullTranscription: boolean;
  onToggleFull: (checked: boolean) => void;
  onSegmentClick: (segmentId: string) => void;
}

export function TranscriptionPanel({ 
  timeline, 
  showFullTranscription, 
  onToggleFull, 
  onSegmentClick 
}: TranscriptionPanelProps) {
  return (
    <details className="border-b border-[#2e2e2e]" open>
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
      
      <ScrollArea className="h-[300px]">
        <div className="space-y-3 p-4">
          {(showFullTranscription ? timeline?.transcription : timeline?.current_sequence)
            ?.filter(seg => seg.text && seg.text.trim().length > 0)
            .sort((a, b) => a.start - b.start)
            .map((seg, idx) => (
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
  );
}
