"""
orchestrator/task_graph.py

Parses LLM tool call responses into an ordered execution plan.

Cycle detection uses topological sort (Kahn's algorithm).
Output: list of parallel groups — each group runs concurrently with asyncio.gather().

Example:
  Tool calls: [search.find_segments, edit.keep_only (depends_on search)]
  Output: [[search.find_segments], [edit.keep_only]]
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from agents.base import ToolCall

logger = logging.getLogger(__name__)


class TaskGraph:
    """
    Builds an ordered execution plan from a flat list of ToolCalls.

    Supports:
    - Parallel execution: tools without mutual dependencies run in the same group.
    - Sequential execution: tools with depends_on run after their dependencies.
    - Cycle detection: raises ValueError if depends_on creates a cycle.
    """

    @staticmethod
    def build(tool_calls: list[ToolCall]) -> list[list[ToolCall]]:
        """
        Convert a flat ToolCall list into ordered parallel execution groups.

        Returns list[list[ToolCall]] where:
        - Each inner list is a group of ToolCalls that can run concurrently.
        - Groups are ordered: group[i] must fully complete before group[i+1] starts.

        Raises:
            ValueError: if the depends_on graph contains a cycle.
        """
        if not tool_calls:
            return []

        # Build name → call map (allow multiple calls to same tool)
        # Since tool names can repeat, we use call_id (index) as the node key.
        n = len(tool_calls)
        name_to_indices: dict[str, list[int]] = defaultdict(list)
        for i, call in enumerate(tool_calls):
            name_to_indices[call.name].append(i)

        # Build adjacency list and in-degree map
        # Edge: (i → j) means call[i] must complete before call[j]
        in_degree: list[int] = [0] * n
        successors: list[list[int]] = [[] for _ in range(n)]  # i → list of j

        for j, call in enumerate(tool_calls):
            for dep_name in call.depends_on:
                dep_indices = name_to_indices.get(dep_name, [])
                for i in dep_indices:
                    if i != j:
                        successors[i].append(j)
                        in_degree[j] += 1

        # Kahn's topological sort — produces level-by-level groups
        queue: deque[int] = deque()
        for i in range(n):
            if in_degree[i] == 0:
                queue.append(i)

        groups: list[list[ToolCall]] = []
        visited = 0

        while queue:
            # Collect all nodes at current level (same in-degree)
            level_size = len(queue)
            group_indices: list[int] = []
            for _ in range(level_size):
                idx = queue.popleft()
                group_indices.append(idx)
                visited += 1
                for successor in successors[idx]:
                    in_degree[successor] -= 1
                    if in_degree[successor] == 0:
                        queue.append(successor)

            group = [tool_calls[i] for i in group_indices]
            groups.append(group)

        if visited != n:
            raise ValueError(
                "Cycle detected in tool depends_on graph. "
                "Cannot build execution order."
            )

        logger.debug(
            "TaskGraph: %d tool calls → %d execution groups: %s",
            n,
            len(groups),
            [[c.name for c in g] for g in groups],
        )
        return groups

    @staticmethod
    def validate_names(
        tool_calls: list[ToolCall],
        registered_names: set[str],
    ) -> list[str]:
        """
        Return a list of unknown tool names.

        The orchestrator calls this before taking a snapshot — if any unknown
        tool names are returned, execution is aborted (no state changes made).
        """
        unknown = [
            call.name
            for call in tool_calls
            if call.name not in registered_names
        ]
        return unknown
