from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM


class CriticAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "critic", description: str = "Reviews and critiques outputs from other agents, identifies flaws and suggests improvements") -> None:
        super().__init__(
            name=name,
            description=description,
        )
        self._llm = llm

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        """Review and critique an output from another agent."""
        query = getattr(task, 'description', str(task))

        system_prompt = """You are a critic agent. Your job is to review outputs from other agents and provide constructive criticism.
        
        For each review, identify:
        1. Strengths of the work
        2. Potential issues, errors, or inaccuracies
        3. Missing information or gaps
        4. Suggestions for improvement
        5. Overall quality rating (Excellent, Good, Needs Improvement, Poor)
        
        Be concise (under 200 words) and specific.
        Your goal is to help improve the quality of the final output."""

        content, _ = await self._llm.generate(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": query}],
        )

        return content
