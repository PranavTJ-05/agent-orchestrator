from __future__ import annotations

import datetime
from typing import Any

import httpx

from ..core.tool import Tool

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) agent-orchestrator/0.1"
YAHOO = "https://query1.finance.yahoo.com"


class StockQuoteTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="stock_quote",
            description="Get the latest real stock price, day range, 52-week range, volume and recent news "
                        "headlines for a ticker symbol (e.g. TSLA). Use this for any stock price question.",
        )

    async def execute(self, symbol: str) -> dict[str, Any]:
        """Fetch a live quote and headlines from Yahoo Finance.

        Args:
            symbol: Ticker symbol, e.g. TSLA, AAPL
        """
        symbol = symbol.strip().upper()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
                chart = await client.get(f"{YAHOO}/v8/finance/chart/{symbol}",
                                         params={"interval": "1d", "range": "5d"})
                chart.raise_for_status()
                result = chart.json()["chart"]["result"][0]
                news: list[dict[str, str]] = []
                try:
                    found = await client.get(f"{YAHOO}/v1/finance/search",
                                             params={"q": symbol, "newsCount": 5, "quotesCount": 0})
                    news = [
                        {"title": n.get("title", ""), "publisher": n.get("publisher", ""), "url": n.get("link", "")}
                        for n in found.json().get("news", [])
                    ]
                except Exception:
                    pass  # headlines are optional
        except Exception as e:
            return {"error": f"Could not fetch a quote for {symbol}: {e}. Do not guess a price."}

        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0].get("close", []) if c is not None]
        price = meta["regularMarketPrice"]
        prev = closes[-2] if len(closes) >= 2 else None
        as_of = datetime.datetime.fromtimestamp(meta["regularMarketTime"], datetime.UTC)
        quote: dict[str, Any] = {
            "symbol": meta["symbol"],
            "name": meta.get("longName") or meta.get("shortName"),
            "price": price,
            "currency": meta.get("currency"),
            "as_of_utc": as_of.strftime("%Y-%m-%d %H:%M"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "day_low": meta.get("regularMarketDayLow"),
            "day_high": meta.get("regularMarketDayHigh"),
            "week52_low": meta.get("fiftyTwoWeekLow"),
            "week52_high": meta.get("fiftyTwoWeekHigh"),
            "volume": meta.get("regularMarketVolume"),
            "source": f"Yahoo Finance https://finance.yahoo.com/quote/{meta['symbol']}",
        }
        if prev:
            quote["previous_close"] = round(prev, 2)
            quote["change_pct"] = round((price - prev) / prev * 100, 2)
        if news:
            quote["recent_headlines"] = news
        return quote
