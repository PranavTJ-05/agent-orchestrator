from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import jsonschema

from .approvals import ApprovalBroker, PendingApproval
from .connection import ServerConnection
from .models import ApprovalMode, ServerSpec, ServerState, ToolInfo, ToolResult
from .store import ServerStore

CALL_TIMEOUT = float(os.getenv("STUDIO_CALL_TIMEOUT", "60"))
EVENT_ARG_CHARS = 200


def _short(value: Any) -> Any:
    text = str(value)
    return text if len(text) <= EVENT_ARG_CHARS else text[:EVENT_ARG_CHARS] + "…"


class StudioManager:
    """Owns every MCP server connection, the merged tool catalogue, approvals and events."""

    def __init__(
        self,
        store: ServerStore | None = None,
        approvals: ApprovalBroker | None = None,
        public_url: str | None = None,
    ) -> None:
        self.store = store or ServerStore()
        self.approvals = approvals or ApprovalBroker()
        self.approvals.bind_emitter(self._emit)
        self._public_url = public_url or os.getenv("STUDIO_PUBLIC_URL", "http://127.0.0.1:8003")
        self._conns: dict[str, ServerConnection] = {}
        self._specs: dict[str, ServerSpec] = {}
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    # ---- events ------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def _emit(self, kind: str, data: dict[str, Any]) -> None:
        event = {"type": kind, "time": time.time(), **data}
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()  # drop the oldest rather than block or grow without limit
            queue.put_nowait(event)

    # ---- lifecycle -----------------------------------------------------------
    async def start(self) -> None:
        for spec in self.store.load():
            self._specs[spec.id] = spec
            self._make_conn(spec)
            if spec.enabled:
                self._conns[spec.id].start()

    async def stop(self) -> None:
        await asyncio.gather(*(c.stop() for c in self._conns.values()), return_exceptions=True)

    def _make_conn(self, spec: ServerSpec) -> ServerConnection:
        conn = ServerConnection(
            spec, self._emit, oauth_dir=self.store.directory / "oauth",
            redirect_uri=f"{self._public_url}/studio/oauth/callback")
        self._conns[spec.id] = conn
        return conn

    def _persist(self) -> None:
        self.store.save(list(self._specs.values()))

    # ---- server management -----------------------------------------------------
    def states(self) -> list[ServerState]:
        return [self._conns[i].state() for i in self._specs]

    def state(self, server_id: str) -> ServerState:
        return self._require(server_id).state()

    def _require(self, server_id: str) -> ServerConnection:
        if server_id not in self._conns:
            raise KeyError(f"No such server: {server_id}")
        return self._conns[server_id]

    async def add(self, spec: ServerSpec) -> ServerState:
        if spec.id in self._specs:
            raise ValueError(f"A server with id '{spec.id}' already exists")
        self._specs[spec.id] = spec
        conn = self._make_conn(spec)
        self._persist()
        if spec.enabled:
            conn.start()
        self._emit("server_changed", {"id": spec.id})
        return conn.state()

    async def update(self, spec: ServerSpec) -> ServerState:
        old = self._require(spec.id).spec
        spec = spec.merge_secrets(old)
        await self._conns[spec.id].stop()
        self._specs[spec.id] = spec
        conn = self._make_conn(spec)
        self._persist()
        if spec.enabled:
            conn.start()
        self._emit("server_changed", {"id": spec.id})
        return conn.state()

    async def remove(self, server_id: str) -> None:
        conn = self._require(server_id)
        await conn.stop()
        del self._conns[server_id], self._specs[server_id]
        oauth_file = self.store.directory / "oauth" / f"{server_id}.json"
        oauth_file.unlink(missing_ok=True)
        self._persist()
        self._emit("server_removed", {"id": server_id})

    async def set_enabled(self, server_id: str, enabled: bool) -> ServerState:
        conn = self._require(server_id)
        spec = conn.spec.model_copy(update={"enabled": enabled})
        self._specs[server_id] = spec
        await conn.stop()
        conn = self._make_conn(spec)
        self._persist()
        if enabled:
            conn.start()
        self._emit("server_changed", {"id": server_id})
        return conn.state()

    async def reconnect(self, server_id: str) -> ServerState:
        return await self.set_enabled(server_id, True)

    def complete_oauth(self, code: str, state: str | None) -> bool:
        return any(c.auth_state == state and c.complete_auth(code, state) for c in self._conns.values())

    # ---- tools -------------------------------------------------------------------
    def tools(self) -> list[ToolInfo]:
        """Tools from connected servers; blocked servers contribute nothing."""
        out: list[ToolInfo] = []
        for conn in self._conns.values():
            if conn.status == "connected" and conn.spec.approval != ApprovalMode.BLOCK:
                out.extend(conn.tools)
        return out

    def find_tool(self, qualified: str) -> ToolInfo | None:
        return next((t for t in self.tools() if t.qualified == qualified), None)

    async def call(self, tool: ToolInfo, arguments: dict[str, Any], source: str = "agent") -> ToolResult:
        """Validate arguments, ask for approval when required, run the tool, emit events."""
        arguments = arguments or {}
        try:
            jsonschema.validate(arguments, tool.input_schema)
        except jsonschema.SchemaError:
            pass  # the server's own schema is malformed: let the server judge the arguments
        except jsonschema.ValidationError as e:
            where = "/".join(str(p) for p in e.absolute_path) or "arguments"
            return ToolResult(ok=False, text=f"Invalid arguments for {tool.name} ({where}): {e.message}")
        base = {"server": tool.server_id, "tool": tool.name, "source": source,
                "arguments": {k: _short(v) for k, v in arguments.items()}}
        if tool.needs_approval():
            summary = ", ".join(f"{k}={_short(v)}" for k, v in arguments.items())
            approved = await self.approvals.request(PendingApproval(
                server_id=tool.server_id, tool=tool.name, arguments=arguments,
                summary=summary, destructive=tool.destructive))
            if not approved:
                self._emit("tool_denied", base)
                return ToolResult(ok=False, text="The user declined this tool call, so it was NOT run. Do not retry it. Tell the user it was not done because they declined.")
        conn = self._require(tool.server_id)
        self._emit("tool_started", base)
        result = await conn.call_tool(tool.name, arguments, CALL_TIMEOUT)
        self._emit("tool_finished", {**base, "ok": result.ok, "ms": round(result.duration_ms),
                                     "preview": result.text[:200]})
        return result

    def planner_hint(self) -> str:
        """One line telling the planner that an `mcp` agent exists, and what it can reach."""
        tools = self.tools()
        if not tools:
            return ""
        by_server: dict[str, list[str]] = {}
        for t in tools:
            by_server.setdefault(t.server_id, []).append(t.name)
        parts = [f"{sid} ({', '.join(names[:4])}{'…' if len(names) > 4 else ''})"
                 for sid, names in by_server.items()]
        return ("- mcp: use it for ANY task that reads, creates, edits, saves or sends something in the user's "
                "connected tool servers (files, repos, databases, messages, calendars...). Connected: "
                + "; ".join(parts[:8]) + ". Never use write or code for those: write only produces text "
                "and cannot save, send or change anything.")
