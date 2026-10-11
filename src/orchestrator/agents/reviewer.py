from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM


class ReviewerAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "reviewer", description: str = "Performs final validation on outputs, checking completeness, correctness, and consistency before approval") -> None:
        super().__init__(
            name=name,
            description=description,
        )
        self._llm = llm

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        """Perform final validation on a completed output."""
        query = getattr(task, 'description', str(task))

        system_prompt = """You are a reviewer agent. Your job is to perform a final validation gate on completed work before it is delivered.
        
        Evaluate the following:
        1. COMPLETENESS: Does the output address all parts of the original request? Are there any missing sections?
        2. CORRECTNESS: Are there any factual errors, logical inconsistencies, or bugs?
        3. CONSISTENCY: Does the output flow logically? Are there contradictions?
        4. CLARITY: Is the output well-structured and easy to understand?
        
        Based on your evaluation, provide one of the following verdicts:
        - APPROVED: The output meets all requirements and is ready for delivery
        - CHANGES REQUESTED: Specific changes are needed before approval
        - REJECTED: Significant issues that require rework
        
        Keep the reasoning under 150 words. If changes are requested or rejected, specify exactly what needs to be fixed."""

        content, _ = await self._llm.generate(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": query}],
        )

        return content
