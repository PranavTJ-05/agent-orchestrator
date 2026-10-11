from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..core.task import TaskNode
from ..llm.base import LLM

ROUTER_SYSTEM_PROMPT = """You are a router agent. Given a task description and a list of available agents, select the best agent to handle the task.

Respond with ONLY the agent name — nothing else."""


# Planner agent-type names -> registered agent names (avoids an LLM routing call per task)
AGENT_ALIASES = {
    "code": "coding",
    "write": "synthesizer",
    "analyze": "finance",
    "analysis": "finance",
}


class RouterAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "router", description: str = "Routes tasks to the best-suited agent") -> None:
        super().__init__(name=name, description=description)
        self._llm = llm
        self._registry: dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        self._registry[agent.name] = agent

    def register_agents(self, agents: list[BaseAgent]) -> None:
        for a in agents:
            self.register_agent(a)

    async def select(self, task: Task) -> str | None:
        if task.agent and task.agent in self._registry:
            return task.agent

        alias = AGENT_ALIASES.get((task.agent or "").lower())
        if alias and alias in self._registry:
            return alias

        agents_desc = "\n".join(
            f"- {a.name}: {a.description} (tools: {[t.name for t in a.tools]})"
            for a in self._registry.values()
        )

        prompt = f"Task: {task.description}\n\nAvailable agents:\n{agents_desc}\n\nWhich agent should handle this task?"
        content, _ = await self._llm.generate(
            system_prompt=ROUTER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        agent_name = content.strip().lower()
        if agent_name in self._registry:
            return agent_name
        for name in self._registry:
            if name in agent_name:
                return name
        return None

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        agent_name = await self.select(task)
        return agent_name or "no_agent_found"
