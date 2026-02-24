"""
Test AudioAgent standalone
"""
import asyncio
import json
from pathlib import Path
from timeline.state import TimelineState
from agents.audio_agent import AudioAgent

async def test_audio():
    # Find most recent project
    projects_dir = Path(__file__).parent.parent / "projects"
    projects = sorted(projects_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not projects:
        print("No projects found")
        return
    
    project_id = projects[0].name
    print(f"Testing project: {project_id}")
    
    # Load state
    state = TimelineState(project_id, projects_dir=str(projects_dir))
    
    print(f"Source: {state.source_path}")
    print(f"Segments: {state.segment_count()}")
    
    # Check if segments exist
    if state.segment_count() == 0:
        print("No segments! Run transcription first")
        return
    
    # Create AudioAgent
    config = json.load(open(Path(__file__).parent / "config.json"))
    
    def progress_callback(event, data):
        print(f"Progress: {event} - {data}")
    
    agent = AudioAgent(state, config, progress_callback)
    
    print("\nRunning AudioAgent...")
    result = await agent.execute_tool("audio_analyze", {})
    
    print(f"\nResult: {result.success}")
    print(f"Data: {result.data}")
    
    if result.success:
        # Check layers
        print("\nChecking layers...")
        segments = state.get_all_segments()
        for seg_id in list(segments.keys())[:3]:  # Check first 3
            layer = state.get_layer("audio_agent", seg_id)
            print(f"  {seg_id}: {layer}")
    
    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(test_audio())
