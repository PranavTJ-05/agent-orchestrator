from __future__ import annotations

import datetime
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM
from ..tools import DelegateTaskTool, StockQuoteTool, WebSearchTool
from ._tooluse import run_with_tools


class ResearchAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "research", description: str = "Performs web research using search tools") -> None:
        super().__init__(
            name=name,
            description=description,
            tools=[WebSearchTool(), StockQuoteTool(), DelegateTaskTool()]
        )
        self._llm = llm

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        """Research a topic using web search, answering only from the search results."""
        query = getattr(task, 'description', str(task))
        system_prompt = f"""You are a research agent. Today is {datetime.date.today().isoformat()}.
Always use tools for anything factual, current or recent:
- web_search: general facts and news (you may call it more than once with different queries).
- stock_quote: real current price for a stock ticker. Use it for any stock price question; search snippets do not contain prices."""
        return await run_with_tools(
            self._llm, self.tools, query, system_prompt,
            "You are a research agent. Synthesize the search results into a short answer and cite the source URLs.",
        )
