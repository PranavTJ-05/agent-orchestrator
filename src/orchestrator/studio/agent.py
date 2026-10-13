from __future__ import annotations

import asyncio
import datetime
import json
import re
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM
from .manager import StudioManager
from .models import ToolInfo
from .picker import ToolPicker

MAX_STEPS = 6
MAX_CANDIDATES = 8
FIND_TOOLS = "find_tools"

FIND_TOOLS_SCHEMA = {"type": "function", "function": {
    "name": FIND_TOOLS,
    "description": "You only see some of the available tools. Call this with a short description of a capability you need "
                   "(for example: list my files to get a file id, search documents) and the matching tools become available.",
    "parameters": {"type": "object", "properties": {"need": {"type": "string", "description": "What you need to do"}},
                   "required": ["need"]}}}
MAX_RESULT_CHARS_FOR_LLM = 4000
MAX_DEP_CHARS = 1500
MAX_DEPS = 4
MAX_DESCRIPTION_CHARS = 500
MAX_OTHER_NAMES = 60

SYSTEM_PROMPT = """You complete the user's task using the tools provided, which come from MCP servers.
Today is {today}.
- Call a tool whenever the task needs real data or an action; never invent results.
- Use only the information in tool results. If a tool fails, read the error, fix the arguments and retry once.
- You only see some of the tools. If you need another capability (looking up an id, listing or searching things), call find_tools first. Never guess ids or paths.
- To get the id of something by its title or name, use a list tool and match the title exactly; fuzzy search can miss recent items. Never guess ids.
- Prefer a tool described as PREFERRED or taking natural language over one described as ADVANCED or manual.
- Never conclude that something is impossible from the tools you were first shown. If they do not fit, read the list of other tools (when given) and call find_tools with a tool name or the thing you want to make, such as "create a diagram".
- On a diagram or design service, words like frontend, backend, database, architecture, flow or schema describe what to draw: use its diagram tools.
- Never ask the user questions. If a detail is missing, choose a sensible default (private, default folder, standard settings) and proceed.
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


MAX_SCHEMA_DESCRIPTION = 160


def slim_schema(node: Any) -> Any:
    """Shrink a JSON schema for the LLM: long per-field descriptions and examples cost tokens
    on every call. Structure, types, enums and required fields are untouched."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in ("$schema", "title", "examples", "example") and not isinstance(value, dict):
                continue  # annotation keywords (a *property* named "title" is a dict and stays)
            if key == "description" and isinstance(value, str):
                out[key] = value[:MAX_SCHEMA_DESCRIPTION]
            else:
                out[key] = slim_schema(value)
        return out
    if isinstance(node, list):
        return [slim_schema(item) for item in node]
    return node


def to_llm_tool(tool: ToolInfo) -> dict[str, Any]:
    schema = slim_schema(dict(tool.input_schema or {}))
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
        self._add_recommended_twins(candidates, tools)
        schemas = self._schemas(candidates, tools)
        system = SYSTEM_PROMPT.format(today=datetime.date.today().isoformat())
        if picked.low_confidence:  # the shortlist may be wrong: show every other tool by name so the model can ask for one
            others = [t.qualified for t in tools if t.qualified not in candidates][:MAX_OTHER_NAMES]
            if others:
                system += "\nOther tools you can request with find_tools: " + ", ".join(others)
        earlier = dependency_context(task, state)
        first = query if not earlier else f"{query}\n\nResults from earlier steps (use these values):\n{earlier}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": first}]
        attempted: set[str] = set()  # exact write calls already made (even if they timed out)
        ran: list[str] = []  # tools that already executed: their effects cannot be undone by a retry

        try:
            for step in range(MAX_STEPS):
                content, calls = await self._generate(system, messages, schemas, required=step == 0)
                calls = [c for c in calls if c.get("type") == "function"]
                if not calls:
                    return content or "(the model returned no answer)"
                messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
                outputs = await asyncio.gather(*(self._execute(candidates, c, ran, attempted, tools, by_name) for c in calls))
                for call, text in zip(calls, outputs):
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": text})
                schemas = self._schemas(candidates, tools)

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

    @staticmethod
    def _add_recommended_twins(candidates: dict[str, ToolInfo], tools: list[ToolInfo]) -> None:
        """When a server says "ADVANCED, most callers should use X instead", offer X as well."""
        for tool in list(candidates.values()):
            match = re.search(r"should use ([a-z0-9_]+)", tool.description or "", re.IGNORECASE)
            if not match:
                continue
            twin = next((t for t in tools if t.server_id == tool.server_id and t.name == match.group(1)), None)
            if twin is not None and twin.qualified not in candidates and len(candidates) < MAX_CANDIDATES:
                candidates[twin.qualified] = twin

    @staticmethod
    def _schemas(candidates: dict[str, ToolInfo], tools: list[ToolInfo]) -> list[dict[str, Any]]:
        extra = [FIND_TOOLS_SCHEMA] if len(tools) > len(candidates) else []  # nothing left to find otherwise
        return extra + [to_llm_tool(t) for t in candidates.values()]

    async def _find_tools(self, call: dict[str, Any], candidates: dict[str, ToolInfo], tools: list[ToolInfo],
                          by_name: dict[str, ToolInfo]) -> str:
        """Let the model ask for a capability it was not shown; the picker supplies matching tools."""
        try:
            need = str(json.loads(call["function"].get("arguments") or "{}").get("need", "")).strip()
        except ValueError:
            need = ""
        if not need:
            return "Error: find_tools needs a short description in 'need'."
        pool = [t for t in tools if t.qualified not in candidates] or tools
        named = [t for t in pool if t.qualified in need or re.search(rf"\b{re.escape(t.name)}\b", need)]
        if named:  # the model asked for tools by name: no guessing needed
            for t in named[:3]:
                if len(candidates) < MAX_CANDIDATES:
                    candidates[t.qualified] = t
            self.studio._emit("tools_found", {"need": need[:120], "added": [t.qualified for t in named[:3]], "method": "name", "ms": 0})
            return "Now available: " + "; ".join(f"{t.qualified} ({(t.description or '')[:80]})" for t in named[:3])
        found = await self.picker.pick(need, pool, always_rank=True)
        # Jev judges intent; word overlap is exact for lookups ("list files" -> list_files). Use both.
        by_words = self.picker.keyword_pick(need, pool, 2)
        ordered = found.tools[:3] + [p for p in by_words.tools if p.probability >= 0.15]
        added = []
        for p in ordered:
            if p.qualified in by_name and p.qualified not in candidates and len(candidates) < MAX_CANDIDATES:
                candidates[p.qualified] = by_name[p.qualified]
                added.append(p.qualified)
        self.studio._emit("tools_found", {"need": need[:120], "added": added, "method": found.method, "ms": found.ms})
        if not added:
            return "No additional tools matched that need."
        return "Now available: " + "; ".join(f"{q} ({(by_name[q].description or '')[:80]})" for q in added)

    async def _generate(self, system: str, messages: list[dict[str, Any]], schemas: list[dict[str, Any]],
                        required: bool) -> tuple[str, list[dict[str, Any]]]:
        """First step must call a tool. Some providers reject the call outright when the model wants
        to ask a question instead (tool_use_failed): nudge it once to pick defaults and proceed."""
        choice = "required" if required else "auto"
        try:
            return await self._llm.generate(system_prompt=system, messages=messages, tools=schemas, tool_choice=choice)
        except Exception as e:  # noqa: BLE001
            if not (required and "tool_use_failed" in str(e)):
                raise
        nudge = messages + [{"role": "user", "content": "Do not ask questions. Choose sensible defaults and call the most suitable tool now."}]
        return await self._llm.generate(system_prompt=system, messages=nudge, tools=schemas, tool_choice="required")

    async def _execute(self, candidates: dict[str, ToolInfo], call: dict[str, Any], ran: list[str],
                       attempted: set[str], tools: list[ToolInfo], by_name: dict[str, ToolInfo]) -> str:
        name = call["function"]["name"]
        if name == FIND_TOOLS:
            return await self._find_tools(call, candidates, tools, by_name)
        tool = candidates.get(name)
        if tool is None:
            return f"Error: '{name}' is not one of the available tools: {', '.join(candidates)}"
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as e:
            return f"Error: could not parse arguments for {name}: {e}"
        key = f"{tool.qualified}:{json.dumps(args, sort_keys=True, default=str)}"
        if tool.read_only is not True and key in attempted:  # writes only; independent of the approval policy
            return ("Error: this exact call was already made in this task (possibly it timed out but succeeded). "
                    "It was NOT repeated, to avoid creating duplicates.")
        attempted.add(key)
        result = await self.studio.call(tool, args, source="agent")
        ran.append(f"{tool.server_id}.{tool.name}" + ("" if result.ok else " (failed)"))
        text = result.text
        if len(text) > MAX_RESULT_CHARS_FOR_LLM:
            text = text[:MAX_RESULT_CHARS_FOR_LLM] + "... [truncated]"
        return text if result.ok else f"Error: {text}"
