from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from .models import ServerSpec, ServerState, ToolInfo, ToolResult
from .store import write_private

CONNECT_TIMEOUT = 30.0
PING_INTERVAL = 30.0
MAX_BACKOFF = 60.0
MAX_RESULT_CHARS = 8000


def _leaf_message(exc: BaseException) -> str:
    """anyio wraps failures in ExceptionGroups; show the first real cause."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def _safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)


def render_result(result: types.CallToolResult) -> tuple[str, bool]:
    """Flatten MCP content blocks into text the LLM can read. Returns (text, truncated)."""
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        elif isinstance(block, types.ImageContent):
            parts.append(f"[image: {block.mimeType}]")
        elif isinstance(block, types.AudioContent):
            parts.append(f"[audio: {block.mimeType}]")
        elif isinstance(block, types.EmbeddedResource):
            res = block.resource
            parts.append(res.text if isinstance(res, types.TextResourceContents) else f"[binary resource: {res.uri}]")
        elif isinstance(block, types.ResourceLink):
            parts.append(f"[resource: {block.uri}]")
    if not parts and getattr(result, "structuredContent", None):
        parts.append(json.dumps(result.structuredContent, default=str))
    text = "\n".join(parts) or "(empty result)"
    if len(text) > MAX_RESULT_CHARS:
        return text[:MAX_RESULT_CHARS] + f"\n... [truncated {len(text) - MAX_RESULT_CHARS} chars]", True
    return text, False


class FileTokenStorage(TokenStorage):
    """OAuth tokens and dynamic client registration, stored owner-only on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, key: str, value: dict[str, Any]) -> None:
        data = self._read()
        data[key] = value
        write_private(self.path, json.dumps(data))

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        self._write("client_info", info.model_dump(mode="json", exclude_none=True))


class ServerConnection:
    """One MCP server. A single task owns the transport and session so it is entered and
    exited from the same task (an anyio requirement); everything else only awaits calls."""

    def __init__(
        self,
        spec: ServerSpec,
        notify: Callable[[str, dict[str, Any]], None],
        oauth_dir: Path,
        redirect_uri: str,
    ) -> None:
        self.spec = spec
        self._notify = notify
        self._oauth_dir = oauth_dir
        self._redirect_uri = redirect_uri
        self.status: str = "disabled"
        self.error: str | None = None
        self.tools: list[ToolInfo] = []
        self.server_name: str | None = None
        self.server_version: str | None = None
        self.connected_at: float | None = None
        self.auth_url: str | None = None
        self.auth_state: str | None = None
        self._auth_future: asyncio.Future[tuple[str, str | None]] | None = None
        self._session: ClientSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._refresh = asyncio.Event()

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self.status = "connecting"
        self.error = None
        self._task = asyncio.create_task(self._run(), name=f"mcp-{self.spec.id}")

    async def stop(self) -> None:
        self._stop.set()
        if self._auth_future and not self._auth_future.done():
            self._auth_future.cancel()
        if self._task:
            try:
                await asyncio.wait_for(self._task, 10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None
        self._session = None
        self.tools = []
        self.status = "disabled"
        self._notify("server_changed", {"id": self.spec.id})

    def state(self) -> ServerState:
        return ServerState(
            spec=self.spec.redacted(), status=self.status, error=self.error,  # type: ignore[arg-type]
            tool_count=len(self.tools), server_name=self.server_name,
            server_version=self.server_version, connected_at=self.connected_at, auth_url=self.auth_url,
        )

    # ---- OAuth -----------------------------------------------------------
    def complete_auth(self, code: str, state: str | None) -> bool:
        if self._auth_future and not self._auth_future.done():
            self._auth_future.set_result((code, state))
            return True
        return False

    def _oauth_provider(self) -> OAuthClientProvider:
        from pydantic import AnyUrl
        metadata = OAuthClientMetadata(
            client_name="Agent Orchestrator Studio",
            redirect_uris=[AnyUrl(self._redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        )

        async def redirect_handler(url: str) -> None:
            self.auth_url = url
            self.auth_state = (parse_qs(urlparse(url).query).get("state") or [None])[0]
            self.status = "needs_auth"
            self._notify("server_changed", {"id": self.spec.id})

        async def callback_handler() -> tuple[str, str | None]:
            self._auth_future = asyncio.get_running_loop().create_future()
            try:
                return await asyncio.wait_for(self._auth_future, 300)
            finally:
                self.auth_url = None

        return OAuthClientProvider(
            server_url=self.spec.url or "",
            client_metadata=metadata,
            storage=FileTokenStorage(self._oauth_dir / f"{self.spec.id}.json"),
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )

    # ---- connection loop ---------------------------------------------------
    async def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                async with AsyncExitStack() as stack:
                    session = await self._open(stack)
                    attempt = 0
                    await self._serve(session)
            except asyncio.CancelledError:
                raise
            except BaseException as e:  # noqa: BLE001 - report any transport failure
                if self._stop.is_set():
                    break
                self.error = _leaf_message(e)
                self.status = "error"
            finally:
                self._session = None
                self.tools = []
            if self._stop.is_set():
                break
            self._notify("server_changed", {"id": self.spec.id})
            attempt += 1
            delay = min(2 ** attempt, MAX_BACKOFF)
            try:
                await asyncio.wait_for(self._stop.wait(), delay)
            except asyncio.TimeoutError:
                self.status = "connecting"
                self._notify("server_changed", {"id": self.spec.id})

    async def _open(self, stack: AsyncExitStack) -> ClientSession:
        spec = self.spec
        auth = self._oauth_provider() if (spec.oauth and spec.transport != "stdio") else None
        if spec.transport == "stdio":
            params = StdioServerParameters(
                command=spec.command or "", args=spec.args, env=spec.env or None, cwd=spec.cwd)
            read, write = await stack.enter_async_context(stdio_client(params))
        elif spec.transport == "http":
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(spec.url or "", headers=spec.headers or None, auth=auth))
        else:
            read, write = await stack.enter_async_context(
                sse_client(spec.url or "", headers=spec.headers or None, auth=auth))
        session = await stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120),
                          message_handler=self._on_message))
        # OAuth may need the user to log in, so allow longer while waiting for auth
        init = await asyncio.wait_for(session.initialize(), 330 if auth else CONNECT_TIMEOUT)
        self.server_name = init.serverInfo.name
        self.server_version = init.serverInfo.version
        self._session = session
        await self._load_tools()
        self.status = "connected"
        self.error = None
        self.auth_url = None
        self.connected_at = time.time()
        self._notify("server_changed", {"id": spec.id})
        return session

    async def _serve(self, session: ClientSession) -> None:
        """Stay connected: refresh tools on request and ping to detect a dead server."""
        while not self._stop.is_set():
            waiter = asyncio.ensure_future(self._stop.wait())
            refresh = asyncio.ensure_future(self._refresh.wait())
            done, pending = await asyncio.wait({waiter, refresh}, timeout=PING_INTERVAL,
                                               return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            if self._stop.is_set():
                return
            if self._refresh.is_set():
                self._refresh.clear()
                await self._load_tools()
                self._notify("server_changed", {"id": self.spec.id})
            else:
                await asyncio.wait_for(session.send_ping(), 10)  # raises -> reconnect

    async def _on_message(self, message: Any) -> None:
        if isinstance(message, types.ServerNotification) and isinstance(
                message.root, types.ToolListChangedNotification):
            self._refresh.set()

    async def _load_tools(self) -> None:
        assert self._session is not None
        found: list[types.Tool] = []
        cursor: str | None = None
        while True:
            page = await self._session.list_tools(cursor) if cursor else await self._session.list_tools()
            found.extend(page.tools)
            cursor = page.nextCursor
            if not cursor:
                break
        seen: set[str] = set()
        tools = []
        for t in found:
            qualified = _safe_name(f"{self.spec.id}__{t.name}")[:64]
            while qualified in seen:
                qualified = qualified[:60] + "_" + str(len(seen))
            seen.add(qualified)
            ann = t.annotations
            tools.append(ToolInfo(
                server_id=self.spec.id, name=t.name, qualified=qualified,
                description=(t.description or t.title or "").strip(),
                input_schema=t.inputSchema or {"type": "object", "properties": {}},
                read_only=getattr(ann, "readOnlyHint", None), destructive=getattr(ann, "destructiveHint", None),
                approval=self.spec.approval,
            ))
        self.tools = tools

    # ---- calling -----------------------------------------------------------
    async def call_tool(self, name: str, arguments: dict[str, Any], timeout: float) -> ToolResult:
        session = self._session
        if session is None or self.status != "connected":
            return ToolResult(ok=False, text=f"Server '{self.spec.id}' is not connected ({self.status}).")
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(session.call_tool(name, arguments), timeout)
        except asyncio.TimeoutError:
            return ToolResult(ok=False, text=f"Tool '{name}' timed out after {timeout:.0f}s.",
                              duration_ms=(time.monotonic() - started) * 1000)
        except Exception as e:  # noqa: BLE001 - protocol or transport error
            return ToolResult(ok=False, text=f"Tool '{name}' failed: {_leaf_message(e)}",
                              duration_ms=(time.monotonic() - started) * 1000)
        text, truncated = render_result(result)
        return ToolResult(ok=not result.isError, text=text, truncated=truncated,
                          duration_ms=(time.monotonic() - started) * 1000)
