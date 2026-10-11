from __future__ import annotations

import asyncio
import datetime
import json
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM
from .manager import StudioManager
from .models import ToolInfo
from .picker import ToolPicker

MAX_STEPS = 4
MAX_RESULT_CHARS_FOR_LLM = 4000
MAX_DEP_CHARS = 1500
MAX_DEPS = 4
MAX_DESCRIPTION_CHARS = 500

SYSTEM_PROMPT = """You complete the user's task using the tools provided, which come from MCP servers.
Today is {today}.
- Call a tool whenever the task needs real data or an action; never invent results.
- Use only the information in tool results. If a tool fails, read the error, fix the arguments and retry once.
- When you have what you need, reply with a short, direct answer (no tool call)."""


def dependency_context(task: Any, state: ExecutionState | None) -> str:
    """Results of the tasks this one depends on, so values found earlier can be used (truncated)."""
    if state is None or not getattr(task, "deps", None):
        return ""
    by_id = {t.id: t for t in state.tasks}
    parts = []
    for dep_id in task.deps[:MAX_DEPS]:
        dep = by_id.get(dep_id)
        if dep is not None and dep.result:
            text = dep.result if len(dep.result) <= MAX_DEP_CHARS else dep.result[:MAX_DEP_CHARS] + "... [truncated]"
            parts.append(f"- {dep.description}\n  Result: {text}")
    return "\n".join(parts)


def to_llm_tool(tool: ToolInfo) -> dict[str, Any]:
    schema = dict(tool.input_schema or {})
    schema.pop("$schema", None)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {"type": "function", "function": {
        "name": tool.qualified,
        "description": (tool.description or tool.name)[:MAX_DESCRIPTION_CHARS],
        "parameters": schema,
    }}


class McpAgent(BaseAgent):
    """Runs a task with tools from the connected MCP servers.

    The ToolPicker shortlists a few tools (cheap, local), the LLM sees only those schemas and
    does the argument filling, and every call goes through the manager (validation, approval,
    timeouts, events).
    """

    def __init__(self, llm: LLM, studio: StudioManager, picker: ToolPicker | None = None,
                 name: str = "mcp",
                 description: str = "Uses tools from the user's connected MCP servers (files, GitHub, databases, chat, calendars and more)") -> None:
        super().__init__(name=name, description=description)
        self._llm = llm
        self.studio = studio
        self.picker = picker or ToolPicker()

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        query = getattr(task, "description", str(task))
        tools = self.studio.tools()
        if not tools:
            return "No MCP tools are available. Connect a server in the Studio first."
        picked = await self.picker.pick(query, tools)
        self.studio._emit("tools_picked", {
            "task": query[:120], "method": picked.method, "confidence": picked.confidence,
            "ms": picked.ms, "tools": [p.qualified for p in picked.tools]})
        by_name = {t.qualified: t for t in tools}
        candidates = {p.qualified: by_name[p.qualified] for p in picked.tools if p.qualified in by_name}
        schemas = [to_llm_tool(t) for t in candidates.values()]
        system = SYSTEM_PROMPT.format(today=datetime.date.today().isoformat())
        earlier = dependency_context(task, state)
        first = query if not earlier else f"{query}\n\nResults from earlier steps (use these values):\n{earlier}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": first}]
        ran: list[str] = []  # tools that already executed: their effects cannot be undone by a retry

        try:
            for step in range(MAX_STEPS):
                content, calls = await self._llm.generate(
                    system_prompt=system, messages=messages, tools=schemas,
                    tool_choice="required" if step == 0 else "auto")
                calls = [c for c in calls if c.get("type") == "function"]
                if not calls:
                    return content or "(the model returned no answer)"
                messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
                outputs = await asyncio.gather(*(self._execute(candidates, c, ran) for c in calls))
                for call, text in zip(calls, outputs):
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": text})

            messages.append({"role": "user", "content": "Stop calling tools. Answer using what you have so far."})
            content, _ = await self._llm.generate(system_prompt=system, messages=messages)
            return content or "(the model returned no answer)"
        except Exception as e:
            if not ran:
                raise  # nothing happened yet, so the orchestrator may safely retry this task
            # Tools already ran (and may have been approved and had side effects). A retry would
            # repeat them, so report what happened instead of failing the task.
            done = "; ".join(ran)
            return (f"Stopped early because of an error after these tool calls completed: {done}. "
                    f"Error: {type(e).__name__}: {e}")

    async def _execute(self, candidates: dict[str, ToolInfo], call: dict[str, Any], ran: list[str]) -> str:
        name = call["function"]["name"]
        tool = candidates.get(name)
        if tool is None:
            return f"Error: '{name}' is not one of the available tools: {', '.join(candidates)}"
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as e:
            return f"Error: could not parse arguments for {name}: {e}"
        result = await self.studio.call(tool, args, source="agent")
        ran.append(f"{tool.server_id}.{tool.name}" + ("" if result.ok else " (failed)"))
        text = result.text
        if len(text) > MAX_RESULT_CHARS_FOR_LLM:
            text = text[:MAX_RESULT_CHARS_FOR_LLM] + "... [truncated]"
        return text if result.ok else f"Error: {text}"
