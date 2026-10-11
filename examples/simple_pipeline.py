"""
Simple sequential pipeline example.
Shows how to create custom agents and run them through the orchestrator.
"""
import asyncio

from src.orchestrator import AgentOrchestrator, BaseAgent, LLMConfig, Task, ExecutionState
from src.orchestrator.llm import create_llm


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="research", description="Performs web research on topics")
        self._llm = create_llm(LLMConfig())

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return f"Research findings for '{task.description}': [simulated research data]"


class ReportAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="report", description="Generates structured reports")
        self._llm = create_llm(LLMConfig())

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return f"## Report\n\nGenerated report based on: {task.description}"


async def main() -> None:
    llm = create_llm(LLMConfig())
    orchestrator = AgentOrchestrator(llm=llm)

    orchestrator.register_agent(ResearchAgent())
    orchestrator.register_agent(ReportAgent())

    result = await orchestrator.execute(
        "Research quantum computing advancements and create a summary report"
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
