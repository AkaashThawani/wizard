import { Button } from '@/components/ui/button';
import { Upload } from 'lucide-react';

interface AppHeaderProps {
  projectId: string | null;
  onNewProject: () => void;
  onClearProject: () => void;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isCreating?: boolean;
}

export function AppHeader({ 
  projectId, 
  onNewProject, 
  onClearProject, 
  onUpload,
  isCreating 
}: AppHeaderProps) {
  return (
    <header className="flex items-center gap-4 border-b border-[#2e2e2e] bg-[#141414] px-5 py-4 shadow-lg">
      <span className="text-base font-bold tracking-wider text-[#4a9eff]">⬡ WIZARD</span>
      <span className="text-xs text-[#606060]">
        {projectId ? `project: ${projectId}` : 'No project'}
      </span>
      <div className="ml-auto flex gap-3">
        <Button
          onClick={onNewProject}
          disabled={isCreating}
          variant="outline"
          size="sm"
          className="border-[#2e2e2e] bg-[#1c1c1c] text-[#e8e8e8] hover:border-[#4a9eff] hover:bg-[#242424] hover:text-white"
        >
          {isCreating ? 'Creating...' : 'New Project'}
        </Button>
        {projectId && (
          <>
            <Button
              onClick={onClearProject}
              variant="destructive"
              size="sm"
              className="bg-[#dc3545] hover:bg-[#c82333]"
            >
              Clear Project
            </Button>
            <Button
              asChild
              size="sm"
              className="bg-[#4a9eff] hover:bg-[#3a8eef]"
            >
              <label className="cursor-pointer gap-2">
                <Upload className="h-4 w-4" />
                Upload Video
                <input 
                  type="file" 
                  accept="video/*" 
                  onChange={onUpload} 
                  className="hidden" 
                />
              </label>
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
