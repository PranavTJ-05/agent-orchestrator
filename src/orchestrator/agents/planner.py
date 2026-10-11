from __future__ import annotations

import uuid
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..core.task import Plan, TaskNode, TaskStatus
from ..llm.base import LLM

PLANNER_SYSTEM_PROMPT = """You are a planning agent. Given a user goal, decompose it into a sequence of specific, actionable tasks in a DAG (Directed Acyclic Graph) structure.

Each task must have:
- A clear description of what to do
- Its dependencies (list of task IDs it depends on)
- The type of agent best suited (research, code, finance, write, analyze, critic, reviewer)
- Whether it requires human approval (requires_approval: true/false)

Available agent types:
- research: for web research, fact-finding, gathering information
- code: for writing, running, and debugging code
- finance: for financial data analysis and stock information
- write: for drafting text (reports, summaries). It only produces text; it cannot save files or perform actions
- analyze: for data analysis and interpretation
- critic: for reviewing and critiquing outputs from other agents
- reviewer: for final validation and approval of completed work

IMPORTANT: Keep plans small. Use at most 4 tasks, merge related steps, and prefer parallel tasks over long chains.
Only add critic or reviewer tasks if the user explicitly asks for a review or validation. The final report is written by a separate synthesizer, so do not add a writing task for it.

IMPORTANT: Use requires_approval: true for dangerous operations like:
- Deleting databases or files
- Deploying code to production
- Sending emails or messages
- Creating cloud resources
- Making financial transactions

Example output format:
[
  {
    "id": "t1",
    "description": "Collect company info on Nvidia",
    "agent": "research",
    "deps": [],
    "requires_approval": false
  },
  {
    "id": "t2",
    "description": "Gather latest news about Nvidia",
    "agent": "research",
    "deps": [],
    "requires_approval": false
  },
  {
    "id": "t3",
    "description": "Analyze stock metrics for Nvidia",
    "agent": "finance",
    "deps": ["t1", "t2"],
    "requires_approval": false
  }
]

Dependencies mean: a task should only run AFTER all its dependencies are complete.
The DAG is executed in topological waves - tasks with no pending dependencies can run in parallel.
Use deps: [] for tasks that can start immediately."""


class PlannerAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "planner", description: str = "Decomposes goals into task plans") -> None:
        super().__init__(name=name, description=description)
        self._llm = llm
        self.extra_agents: Any = None  # callable returning extra agent lines (e.g. the mcp agent)

    def _system_prompt(self) -> str:
        extra = self.extra_agents() if callable(self.extra_agents) else ""
        if not extra:
            return PLANNER_SYSTEM_PROMPT
        return PLANNER_SYSTEM_PROMPT + "\n\nAdditional agent type available right now (agent: mcp):\n" + extra

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        plan = await self.plan(task.description)
        return plan.model_dump_json(indent=2)

    async def plan(self, goal: str) -> Plan:
        content, tool_calls = await self._llm.generate(
            system_prompt=self._system_prompt(),
            messages=[{"role": "user", "content": goal}],
        )

        import json
        tasks_data = _parse_plan(content)
        if tasks_data is None:
            content2, _ = await self._llm.generate(
                system_prompt=self._system_prompt() + "\n\nCRITICAL: You MUST output valid JSON. Start with [.",
                messages=[{"role": "user", "content": goal}],
            )
            tasks_data = _parse_plan(content2)
        if tasks_data is None:
            tasks_data = [{
                "id": "t1",
                "description": goal,
                "agent": None,
                "deps": [],
            }]

        tasks = []
        for td in tasks_data:
            tasks.append(TaskNode(
                id=td.get("id", f"t_{uuid.uuid4().hex[:6]}"),
                description=td["description"],
                agent=td.get("agent"),
                deps=td.get("deps", []),
                status=TaskStatus.PENDING,
                requires_approval=td.get("requires_approval", False),
            ))

        return Plan(goal=goal, tasks=tasks)


def _parse_plan(text: str) -> list[dict] | None:
    import json
    if not text or not text.strip():
        return None
    # Try finding a JSON array [...]
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start >= 0:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                if depth == 0:
                    try:
                        candidate = text[start:i+1]
                        data = json.loads(candidate)
                        if isinstance(data, dict):
                            data = data.get("tasks", [data])
                        if isinstance(data, list):
                            return data
                    except json.JSONDecodeError:
                        continue
    # Try parsing the whole text
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            data = data.get("tasks", [data])
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None
