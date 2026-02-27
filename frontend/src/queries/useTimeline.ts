import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { UseTimelineOptions } from '@/types/queries';

export function useTimeline(options: UseTimelineOptions) {
  const { projectId, enabled = true } = options;
  
  return useQuery({
    queryKey: ['timeline', projectId],
    queryFn: () => api.getTimeline(projectId!),
    enabled: enabled && !!projectId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}
