from __future__ import annotations

import datetime
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM
from ..tools import DelegateTaskTool, StockQuoteTool, WebSearchTool
from ._tooluse import run_with_tools


class FinanceAgent(BaseAgent):
    def __init__(self, llm: LLM, name: str = "finance", description: str = "Analyzes financial data and stock information") -> None:
        super().__init__(
            name=name,
            description=description,
            tools=[StockQuoteTool(), WebSearchTool(), DelegateTaskTool()]
        )
        self._llm = llm

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        """Analyze financial information using live quotes and web search."""
        query = getattr(task, 'description', str(task))
        system_prompt = f"""You are a finance agent. Today is {datetime.date.today().isoformat()}.
Tools:
- stock_quote: real current price, ranges, volume and headlines for a ticker. ALWAYS use it for any stock price or market question (call it once per company).
- web_search: fundamentals, earnings and news not covered by stock_quote.
Never state a price or financial figure from memory."""
        return await run_with_tools(
            self._llm, self.tools, query, system_prompt,
            "You are a finance agent. Analyze the data: price and trend, valuation context, risks, and one-line takeaway.",
        )
