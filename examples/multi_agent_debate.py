"""
Multi-agent debate pattern.
Three agents analyze a question from different angles, then a critic synthesizes.
"""
import asyncio

from src.orchestrator import AgentOrchestrator, BaseAgent, LLMConfig, Task, ExecutionState
from src.orchestrator.llm import create_llm


class OptimistAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="optimist", description="Analyzes opportunities and upsides")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Bull Case:**\n"
            "- Strong market tailwinds and growing TAM\n"
            "- Innovative product pipeline\n"
            "- Solid balance sheet with low debt"
        )


class PessimistAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="pessimist", description="Analyzes risks and downsides")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Bear Case:**\n"
            "- Increasing regulatory scrutiny\n"
            "- Competitive pressures compressing margins\n"
            "- Valuation at historical highs"
        )


class CriticAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="critic", description="Weighs evidence and produces balanced conclusions")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Balanced Verdict:**\n\n"
            "After weighing both perspectives, the company presents a mixed outlook.\n"
            "Near-term risks are manageable but medium-term competitive threats are real.\n"
            "Recommendation: HOLD with a focus on upcoming product launch as catalyst."
        )


async def main() -> None:
    llm = create_llm(LLMConfig())
    orchestrator = AgentOrchestrator(llm=llm)

    orchestrator.register_agent(OptimistAgent())
    orchestrator.register_agent(PessimistAgent())
    orchestrator.register_agent(CriticAgent())

    result = await orchestrator.execute(
        "Should I invest in the AI semiconductor sector? Analyze both sides."
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
