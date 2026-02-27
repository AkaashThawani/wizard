import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useWizardStore } from '@/store/useWizardStore';

export function useCreateProject() {
  const queryClient = useQueryClient();
  const setProject = useWizardStore((state) => state.setProject);
  
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: (data) => {
      setProject(data.project_id);
      queryClient.invalidateQueries({ queryKey: ['timeline'] });
    },
  });
}

export function useUploadVideo() {
  const queryClient = useQueryClient();
  const setVideoBlobUrl = useWizardStore((state) => state.setVideoBlobUrl);
  
  return useMutation({
    mutationFn: ({ projectId, file }: { projectId: string; file: File }) => {
      // Store blob URL for immediate playback
      const blobUrl = URL.createObjectURL(file);
      setVideoBlobUrl(blobUrl);
      return api.uploadVideo(projectId, file);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['timeline', variables.projectId] });
    },
  });
}

export function useExportTimeline() {
  return useMutation({
    mutationFn: ({ projectId, resolution = 'preview', outputName = 'export' }: {
      projectId: string;
      resolution?: 'preview' | 'full';
      outputName?: string;
    }) => api.exportTimeline(projectId, resolution, outputName),
  });
}
