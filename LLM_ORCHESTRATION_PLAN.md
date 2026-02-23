# LLM Orchestration Implementation Plan

## [Overview]
Add LLM-based tool orchestration to enable natural language understanding and intelligent tool calling, replacing the current keyword-based intent detection system.

The current system has all required infrastructure (LLM client, tool definitions, agent registry, prompts) but uses keyword regex matching instead of LLM intelligence. This creates a disconnect where the system can't understand requests like "add fade transition to first clip" because it only routes to agents without parsing parameters or understanding intent.

The AGENTIC_CHAT_FEATURE_PLAN.md marks all phases as complete, but Phase 4 "chained workflows" was never properly implemented - the system needs LLM orchestration to intelligently call multiple tools in sequence based on natural language understanding.

## [Types]
No new types needed - all required types already exist.

**Existing Types (in orchestrator/graph_types.py)**:
- `AgentState`: Contains prompt, project_id, tool_calls, results, messages, etc.
- `Tool`: name, description, parameters, depends_on (in agents/base.py)
- `ToolCall`: name, params, depends_on, call_id (in agents/base.py)
- `ToolResult`: success, data, error (in agents/base.py)

These types already support everything needed for LLM orchestration.

## [Files]
Add LLM-based orchestration by creating one new node file and modifying the prompt graph.

**New Files**:
- `backend/orchestrator/llm_orchestrator_node.py`
  - Purpose: LLM agent node that uses llm_client.tool_call() to understand prompts
  - Contains: `make_llm_orchestrator_node()` factory function
  - Functionality: Gets all tools → calls LLM → executes tool calls → returns results

**Modified Files**:
- `backend/orchestrator/prompt_graph.py`
  - Change: Replace intent-based routing with single LLM orchestrator node
  - Remove: route_by_intent(), all agent-specific nodes
  - Add: Single llm_orchestrator_node that handles everything
  
- `backend/llm/prompts.py`
  - Change: Enhance ORCHESTRATOR_SYSTEM prompt with tool examples
  - Add: Context about available operations and response format

**No Changes Needed**:
- `backend/llm/client.py` - Already has `tool_call()` method ✅
- `backend/agents/base.py` - Tool structure perfect ✅
- `backend/agents/registry.py` - `all_tools()` and `get_agent()` ready ✅
- `backend/app.py` - WebSocket handler already saves to history ✅

## [Functions]
Create LLM orchestration node and modify graph creation.

**New Functions**:

1. **`make_llm_orchestrator_node(registry, timeline_state, llm_client, config)`**
   - File: `backend/orchestrator/llm_orchestrator_node.py`
   - Purpose: Factory function that creates LLM orchestrator node
   - Returns: async function that processes prompts via LLM
   - Logic:
     - Get all tools from registry.all_tools()
     - Build timeline context from timeline_state
     - Call llm_client.tool_call() with ORCHESTRATOR_SYSTEM prompt
     - Execute each returned ToolCall via registry.get_agent().execute_tool()
     - Aggregate results and build user-friendly response

2. **`async llm_orchestrator_node(state: AgentState) -> AgentState`**
   - File: `backend/orchestrator/llm_orchestrator_node.py` (inner function)
   - Purpose: The actual node that processes chat messages
   - Parameters: state containing prompt and project_id
   - Returns: Updated state with results, summary, success flag
   - Algorithm:
     ```python
     1. Extract prompt from state
     2. Get all tools from registry
     3. Build timeline context (segments, current_sequence)
     4. Call LLM: llm_client.tool_call(ORCHESTRATOR_SYSTEM, prompt, tools, context)
     5. For each ToolCall returned:
        - Get agent from registry
        - Execute tool
        - Collect result
     6. Aggregate results into summary
     7. Return updated state
     ```

3. **`_build_timeline_context(timeline_state) -> dict`**
   - File: `backend/orchestrator/llm_orchestrator_node.py` (helper function)
   - Purpose: Extract relevant timeline info for LLM context
   - Returns: Dict with segments, current_sequence, segment_count
   - Keep compact - only essential info for LLM

**Modified Functions**:

1. **`create_prompt_workflow(registry, timeline_state, llm_client, config)`**
   - File: `backend/orchestrator/prompt_graph.py`
   - Current: Creates graph with intent router → multiple agent nodes
   - New: Create graph with single llm_orchestrator_node
   - Changes:
     - Remove: make_search_node, make_edit_node, make_export_node, etc.
     - Remove: route_by_intent conditional edge
     - Add: Single llm_orchestrator_node from make_llm_orchestrator_node()
     - Simplify: START → llm_orchestrator → END

**Removed Functions**:
- `route_by_intent()` in prompt_graph.py - replaced by LLM
- All nodes in prompt_nodes.py - replaced by single LLM orchestrator

## [Classes]
No new classes needed - orchestrator node uses existing AgentState class.

**Existing Classes Used**:
- `AgentState` (orchestrator/graph_types.py) - State container
- `Tool`, `ToolCall`, `ToolResult` (agents/base.py) - Tool infrastructure
- `LLMClient` (llm/client.py) - Already has tool_call() method
- `AgentRegistry` (agents/registry.py) - Tool discovery and agent lookup

## [Dependencies]
No new dependencies - all required packages already installed.

**Already Available**:
- `langgraph` - StateGraph, checkpointing
- `anthropic` / `openai` / `google-generativeai` - LLM providers
- All agent dependencies already in requirements.txt

## [Testing]
Test natural language understanding and multi-step workflows.

**Unit Tests** (backend/tests/test_llm_orchestrator.py):
```python
- test_build_timeline_context() - Context format correct
- test_tool_execution_single() - Single tool call works
- test_tool_execution_multiple() - Multiple tools in sequence
- test_parameter_extraction() - "first clip" → segment_id parsed
- test_error_handling() - Failed tool calls handled gracefully
```

**Integration Tests**:
```python
- test_search_workflow() - "find clips with basketball"
- test_edit_workflow() - "add fade transition to first clip"  
- test_chained_workflow() - "find X and trim them and export"
- test_natural_language() - Various phrasings work
- test_context_awareness() - LLM uses timeline context
```

**Manual Testing Scenarios**:
1. "find clips with balls" → search.find_segments called
2. "add fade transition to first clip" → edit.set_transition with correct segment
3. "trim 2 seconds from start of segment 1" → edit.trim_segment with params
4. "find basketball clips and add slow motion" → search → edit chain
5. "make the video brighter" → Should explain not possible with current tools

## [Implementation Order]
Build and test incrementally to minimize risk.

### Step 1: Create LLM Orchestrator Node
**File**: `backend/orchestrator/llm_orchestrator_node.py`
- Implement `_build_timeline_context()` helper
- Implement `make_llm_orchestrator_node()` factory
- Implement tool execution loop
- Add error handling and logging
- Write unit tests

### Step 2: Update System Prompt
**File**: `backend/llm/prompts.py`
- Enhance ORCHESTRATOR_SYSTEM with examples
- Add context explanation
- Document response format expectations
- Keep concise to avoid token waste

### Step 3: Modify Prompt Graph
**File**: `backend/orchestrator/prompt_graph.py`
- Import new llm_orchestrator_node
- Replace conditional routing with single node
- Remove old node imports
- Update graph compilation
- Maintain checkpoint compatibility

### Step 4: Test Single Tool Calls
- Test: "find clips with basketball" 
- Verify: search.find_segments executed correctly
- Check: Timeline updated, chat shows results
- Debug: Parameter extraction issues

### Step 5: Test Multi-Tool Workflows  
- Test: "find clips and add effects"
- Verify: Multiple tools execute in sequence
- Check: Context maintained between calls
- Debug: Dependency handling

### Step 6: Test Error Cases
- Test: Invalid requests ("delete the video")
- Test: Missing segments ("trim segment 999")
- Test: Tool failures
- Verify: Graceful error messages

### Step 7: Production Validation
- Test with real videos and conversations
- Monitor LLM token usage
- Verify chat history persistence
- Check timeline consistency after operations

## Implementation Notes

### Why This Was Missed
The AGENTIC_CHAT_FEATURE_PLAN.md focused on infrastructure (WebSocket, SqliteSaver, tool definitions) but never connected the LLM to actually use those tools intelligently. The prompt_nodes.py file has nodes that route to agents but don't use the LLM - it's just Python code that returns errors like "Edit operations require specific tool calls".

### Key Insights
1. **All Infrastructure Exists**: LLM client, tools, registry, prompts all ready
2. **Simple Fix**: Just call `llm_client.tool_call()` with `registry.all_tools()`
3. **No Restructuring**: Don't need to change agents, tools, or state management
4. **Drop-in Replacement**: New orchestrator node replaces keyword routing

### Critical Success Factors
1. **Context Quality**: Give LLM enough timeline info but keep it compact
2. **Tool Descriptions**: Ensure Tool.description is clear and actionable
3. **Error Handling**: LLM might call non-existent tools or wrong params
4. **Response Format**: Build user-friendly summaries from tool results

### Potential Issues
1. **Token Costs**: LLM calls for every chat message (mitigate: use cheaper models)
2. **Latency**: LLM + tool execution slower than keywords (acceptable for chat)
3. **Accuracy**: LLM might misunderstand (mitigate: good prompts and examples)
4. **Context Size**: Large timelines won't fit (mitigate: summarize context)

### Migration Strategy
- Keep old /prompt endpoint with keyword routing (for backwards compat)
- New chat endpoint uses LLM orchestration
- Gradual rollout: test extensively before making default

---

**Document Status**: Ready for Implementation
**Estimated Implementation Time**: 2-3 hours
**Risk Level**: Low (all infrastructure exists, isolated changes)
**Dependencies**: None (everything already in place)
