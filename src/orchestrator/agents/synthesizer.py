from __future__ import annotations

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..core.task import TaskNode
from ..llm.base import LLM

SYNTHESIZER_SYSTEM_PROMPT = """You are a synthesizer agent. Given a user's original goal and the results from multiple completed tasks, combine them into a coherent, well-structured final response.

Only state that something was saved, sent, created or changed if a task result says so; never claim an action that no task result shows. If a requested action is not evidenced, say it was not done.
Be concise: keep the answer under about 400 words, lead with the direct answer, and include only the findings that matter. Do not repeat task results verbatim."""

# Character budgets keep the final prompt small enough for low per-minute token limits (~4 chars/token).
MAX_CHARS_PER_RESULT = 2000
MAX_CHARS_TOTAL = 8000


def _truncate(text: str, limit: int) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


class SynthesizerAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "synthesizer", description: str = "Combines task results into a final response") -> None:
        super().__init__(name=name, description=description)
        self._llm = llm

    async def synthesize(self, goal: str, completed: list[Task]) -> str:
        parts = [
            f"Task: {_truncate(t.description, 200)}\nResult: {_truncate(t.result, MAX_CHARS_PER_RESULT)}"
            for t in completed if t.result
        ]
        results_str = _truncate("\n\n".join(parts), MAX_CHARS_TOTAL)
        prompt = f"Original goal: {goal}\n\nTask results:\n{results_str}\n\nCombine these into a final response."
        content, _ = await self._llm.generate(
            system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return content

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        if state is None:
            return ""
        # A "write" task drafts what its own description asks for from the tasks it depends on.
        deps = [t for t in state.tasks if t.id in task.deps and t.result]
        return await self.synthesize(task.description, deps or state.completed_tasks)
