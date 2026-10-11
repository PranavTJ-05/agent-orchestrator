from __future__ import annotations

import asyncio
import datetime
import json
from typing import Any

from ..core.tool import Tool
from ..llm.base import LLM

MAX_CHARS_PER_TOOL_RESULT = 3000

GROUNDING_RULES = """Rules:
- Today's date is {today}. Use ONLY the tool results below for facts, numbers, prices and dates; never use memorised figures.
- Quote the date/time of any price and name the source.
- If the tool results do not contain something, say it is unavailable instead of guessing.
- Be concise (under 250 words)."""


async def _call_tool(tools: list[Tool], tool_call: dict[str, Any]) -> tuple[str, str]:
    name = tool_call["function"]["name"]
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        return name, f"Error: unknown tool {name}"
    try:
        args = json.loads(tool_call["function"]["arguments"] or "{}")
        result = await tool.execute(**args)
    except Exception as e:
        return name, f"Error running {name}: {e}"
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(text) > MAX_CHARS_PER_TOOL_RESULT:
        text = text[:MAX_CHARS_PER_TOOL_RESULT] + "... [truncated]"
    return name, text


async def run_with_tools(
    llm: LLM,
    tools: list[Tool],
    query: str,
    system_prompt: str,
    answer_prompt: str,
    require_tool: bool = True,
) -> str:
    """Let the model pick tools, run every requested tool, then answer from the results only.

    With require_tool the first call must use a tool, so facts always come from tool results.
    """
    content, tool_calls = await llm.generate(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": query}],
        tools=[t.to_llm_tool() for t in tools],
        tool_choice="required" if require_tool else "auto",
    )
    calls = [c for c in tool_calls if c.get("type") == "function"]
    if not calls:
        return content

    results = await asyncio.gather(*(_call_tool(tools, c) for c in calls))
    context = f"Request: {query}\n\n" + "\n\n".join(f"[{name} result]\n{text}" for name, text in results)
    rules = GROUNDING_RULES.format(today=datetime.date.today().isoformat())
    final, _ = await llm.generate(
        system_prompt=f"{answer_prompt}\n\n{rules}",
        messages=[{"role": "user", "content": context}],
    )
    return final
