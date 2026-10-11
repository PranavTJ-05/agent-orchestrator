"""
Investment report generation — demonstrates multi-agent coordination.
Simulates a full pipeline: news → finance → research → report.
"""
import asyncio

from src.orchestrator import AgentOrchestrator, BaseAgent, LLMConfig, Task, ExecutionState
from src.orchestrator.llm import create_llm


class NewsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="news", description="Fetches latest news about companies")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Latest News:**\n"
            "- Company announced Q2 earnings beat expectations\n"
            "- New product launch scheduled for next quarter\n"
            "- Analyst upgrades stock to 'buy'"
        )


class FinanceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="finance", description="Analyzes stock metrics and financial data")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Financial Metrics:**\n"
            "- P/E Ratio: 25.4\n"
            "- Market Cap: $800B\n"
            "- Revenue Growth: 18% YoY\n"
            "- EPS: $6.32"
        )


class CompetitorAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="competitor_analysis", description="Compares companies against competitors")

    async def run(self, task: Task, state: ExecutionState | None = None) -> str:
        return (
            "**Competitor Comparison:**\n"
            "- Competitor A: Lower margins, higher R&D spend\n"
            "- Competitor B: Better market share, slower growth\n"
            "- Differentiating factor: proprietary technology stack"
        )


async def main() -> None:
    llm = create_llm(LLMConfig())
    orchestrator = AgentOrchestrator(llm=llm)

    orchestrator.register_agent(NewsAgent())
    orchestrator.register_agent(FinanceAgent())
    orchestrator.register_agent(CompetitorAgent())

    result = await orchestrator.execute(
        "Analyze Tesla stock: find recent news, analyze financial metrics, "
        "compare with competitors, and create an investment report"
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
