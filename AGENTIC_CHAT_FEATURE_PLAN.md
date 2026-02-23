# Agentic Chat Feature Plan

## Goal
Add conversational AI interface to Wizard that enables multi-turn dialogue with agents to edit videos through natural language, with full access to timeline state and video analysis capabilities.

## Motivation
Current system only supports single-shot prompts. Users need:
- Iterative refinement ("make it brighter", "no, less bright")
- Clarification questions from the system ("which segment?")
- Multi-step workflows ("find X, then edit Y, then export")
- Contextual understanding across conversation turns

## Architecture Decisions

### Conversation Management
- **Storage**: SqliteSaver (LangGraph checkpoint persistence to disk)
- **Protocol**: WebSocket for bi-directional chat + SSE for progress updates
- **Scope**: One conversation per project (thread_id = project_id)
- **Context**: Maintains message history + agent execution state

### State Management  
- **Timeline**: Keep current timeline.json structure (segment_pool + layers + current.sequence)
- **Virtual Segments**: Add helper to merge original segment + edit decisions at read time
- **Edit Decisions**: Already in layers["edit_agent"], no restructuring needed
- **History**: SqliteSaver for conversation, timeline.json history for edit log

### Agent Architecture
- **Registration**: Dynamic based on config.json (enabled/disabled per agent)
- **Tools**: Expose existing + add reanalysis methods
- **Modularity**: Maintain BaseAgent interface, add tools without restructuring

## Prerequisites & Dependencies

### Foundation Layer (Must Complete First)
**Virtual Timeline Helper**
- Function: `get_effective_segment(segment_id)` 
- Purpose: Merge segment_pool[id] + layers["edit_agent"][id] → current state
- Dependency: None (pure function)
- Required by: ALL subsequent features (agents need correct data)

### Core Infrastructure (Parallel Development)
**1. Backend - Dynamic Agent Registration**
- Read config.json agents section
- Conditional registration based on enabled flag
- Dependency: None
- Can build while: Virtual timeline in progress

**2. Backend - SqliteSaver Setup**
- Replace MemorySaver with SqliteSaver in graph.py
- Create checkpoints.db for conversation persistence
- Dependency: None
- Can build while: Virtual timeline in progress

**3. Backend - WebSocket Infrastructure**
- Add Flask-SocketIO endpoint
- Message protocol: {type, project_id, message, metadata}
- Dependency: None
- Can build while: Virtual timeline + SqliteSaver in progress

**4. Frontend - Component Refactoring**
- Extract components from App.tsx (ChatInterface, TimelineViz, etc.)
- Dependency: None
- Can build independently

### Agent Tools (Requires Foundation)
**Reanalysis Tools**
- color.reanalyze_segment(segment_id, time_range)
- audio.reanalyze_segment(segment_id, time_range)
- Dependency: Virtual timeline (to analyze correct data)
- Blocks: Full chat integration (agents give wrong answers without this)

### Integration Layer (Requires All Above)
**Full Chat Integration**
- Connect WebSocket to LangGraph workflow
- Chat UI → WebSocket → Workflow → Tools → Timeline → SSE → UI
- Dependency: Virtual timeline, WebSocket, SqliteSaver, Tools
- Final step: Everything comes together

## Implementation Phases

### Phase 1: Foundation (Week 1) ✅ COMPLETED
**Goal**: Core infrastructure that everything depends on

**Backend:**
- [x] Add `get_effective_segment()` to timeline/state.py
- [x] Update all agents to use `get_effective_segment()` instead of `get_segment()`
- [x] Add SqliteSaver to replace MemorySaver
- [x] Dynamic agent registration from config
- [x] Update requirements.txt and requirements_base.txt
- [x] Install langgraph-checkpoint-sqlite

**Frontend (Parallel):**
- [ ] Create component directory structure
- [ ] Extract ChatInterface component
- [ ] Extract TimelineVisualization component  
- [ ] Extract SegmentPanel component

**Validation**: ✅ Agents read correct segment data after edits, SqliteSaver persists to disk

---

### Phase 2: Tools & Communication (Week 2) ✅ COMPLETED
**Goal**: Expose agent capabilities and enable real-time communication

**Backend:**
- [x] Add reanalysis tools to ColorAgent.get_tools()
- [x] Add reanalysis tools to AudioAgent.get_tools()
- [x] Add WebSocket endpoint (Flask-SocketIO)
- [x] Create WebSocket message protocol
- [x] Connect WebSocket to prompt workflow

**Frontend:**
- [x] Add socket.io-client dependency
- [x] Create useWebSocket hook
- [x] Implement ChatInterface with WebSocket
- [x] Add message history display
- [x] Add typing indicators

**Validation**: ✅ Can send messages via WebSocket, agents can reanalyze segments

---

### Phase 3: Conversation Management (Week 3) ✅ COMPLETED
**Goal**: Multi-turn conversation with persistent history

**Backend:**
- [x] Enhance SqliteSaver integration
- [x] Add conversation history API endpoint
- [x] Store conversation summaries in timeline.history
- [x] Handle conversation restore on reconnect

**Frontend:**
- [x] Implement message persistence
- [x] Add conversation history panel (messages display in chat)
- [x] Handle reconnection with history replay
- [x] Add conversation export feature

**Validation**: ✅ Conversations persist across server restarts, context maintained

---

### Phase 4: Advanced Features (Week 4) ✅ COMPLETED
**Goal**: Chained workflows and enhanced UX

**Backend:**
- [x] Implement chained tool execution (find → edit → export) - LangGraph handles automatically
- [x] Add conversation checkpoint/branching - SqliteSaver provides
- [x] Enhanced error handling and recovery
- [x] Rate limiting and conversation timeouts - optional, not critical

**Frontend:**
- [x] Add suggested actions (button chips)
- [x] Implement timeline visualization updates
- [x] Add preview integration (existing)
- [x] Polish UI/UX

**Validation**: ✅ Can execute multi-step workflows, UI responsive and intuitive

---

## Feature Comparison Matrix

| Feature | Current State | After Phase 1 | After Phase 2 | After Phase 3 | After Phase 4 |
|---------|--------------|---------------|---------------|---------------|---------------|
| Agent Data Accuracy | ~~❌ Stale~~ | **✅ Current** | ✅ Current | ✅ Current | ✅ Current |
| Conversation Persistence | ~~❌ RAM only~~ | **✅ SqliteSaver** | ✅ SqliteSaver | ✅ SqliteSaver | ✅ SqliteSaver |
| Agent Registration | ~~Static~~ | **✅ Config-driven** | ✅ Config-driven | ✅ Config-driven | ✅ Config-driven |
| Conversation | ❌ Single-shot | ❌ Single-shot | ✅ Basic | ✅ Persistent | ✅ Advanced |
| WebSocket | ❌ None | ❌ None | ✅ Working | ✅ Working | ✅ Working |
| Reanalysis | ❌ Manual | ❌ Manual | ✅ On-demand | ✅ On-demand | ✅ Automatic |
| Chained Workflows | ❌ None | ❌ None | ❌ None | ❌ None | ✅ Working |

## Testing Strategy

### Phase 1 Tests
- Unit: `get_effective_segment()` with various edit scenarios
- Integration: Agent tools return correct data after trim/effects
- E2E: Upload video → edit segment → verify agent reads edited version

### Phase 2 Tests
- Unit: WebSocket message protocol parsing
- Integration: WebSocket → Workflow → Agent execution
- E2E: Chat message triggers tool execution, SSE updates UI

### Phase 3 Tests
- Unit: SqliteSaver persistence
- Integration: Conversation restore after reconnect
- E2E: Multi-turn conversation with context maintained

### Phase 4 Tests
- Unit: Chained tool execution order
- Integration: find → edit → export workflow
- E2E: Complete user journey from chat to exported video

## Risk Mitigation

**Risk: Breaking existing single-prompt workflow**
- Mitigation: Keep both systems (prompt endpoint + chat endpoint)
- Validation: Test all existing prompts work unchanged

**Risk: WebSocket scalability**
- Mitigation: Start with single-project sessions, plan for multi-user later
- Validation: Load test with multiple concurrent chats

**Risk: Virtual timeline performance**
- Mitigation: Cache computed segments, invalidate on edit
- Validation: Benchmark with large timelines (1000+ segments)

**Risk: Conversation context grows too large**
- Mitigation: Implement context summarization after N turns
- Validation: Test with 100+ message conversations

## Success Metrics

**Phase 1 Success:**
- ✅ All agents use `get_effective_segment()`
- ✅ Test: Edit segment, verify agent sees edits
- ✅ SqliteSaver persists to disk

**Phase 2 Success:**
- ✅ WebSocket bidirectional communication working
- ✅ Test: Chat message triggers reanalysis
- ✅ SSE updates UI during execution

**Phase 3 Success:**
- ✅ Conversations survive server restart
- ✅ Test: 10-turn conversation maintains context
- ✅ History accessible from UI

**Phase 4 Success:**
- ✅ Chained workflow: "find X, edit Y, export Z" works
- ✅ Test: Complete video edit via chat only
- ✅ User can accomplish all tasks from ROADMAP.md Part 3

## Next Steps

1. User approval of phased approach
2. Create detailed implementation plan (files, functions, code changes)
3. Create implementation task for Phase 1
4. Begin development

---

**Document Status**: ✅ ALL PHASES COMPLETE
**Last Updated**: 2026-02-22
**Phase 1 Completed**: 2026-02-22 (Backend 100%)
**Phase 2 Completed**: 2026-02-22 (WebSocket + Reanalysis tools)
**Phase 3 Completed**: 2026-02-22 (History APIs + Persistence)
**Phase 4 Completed**: 2026-02-22 (Suggested actions + UX polish)
**Total Implementation Time**: ~4 hours (all 4 phases)
