from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class PendingApproval(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    server_id: str
    tool: str
    arguments: dict[str, Any]
    summary: str = ""
    destructive: bool | None = None
    created_at: float = Field(default_factory=time.time)


class ApprovalBroker:
    """Holds tool calls that need a human decision.

    The API server leaves `handler` unset, so requests wait for the UI to resolve them.
    The CLI installs a terminal prompt as `handler`. Unanswered requests are denied.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout
        self.handler: Callable[[PendingApproval], Awaitable[bool]] | None = None
        self._pending: dict[str, tuple[PendingApproval, asyncio.Future[bool]]] = {}
        self._emit: Callable[[str, dict[str, Any]], None] = lambda *_: None

    def bind_emitter(self, emit: Callable[[str, dict[str, Any]], None]) -> None:
        self._emit = emit

    def pending(self) -> list[PendingApproval]:
        return [p for p, f in self._pending.values() if not f.done()]

    async def request(self, item: PendingApproval) -> bool:
        if self.handler is not None:
            try:
                return await asyncio.wait_for(self.handler(item), self.timeout)
            except asyncio.TimeoutError:
                return False
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[item.id] = (item, future)
        self._emit("approval_requested", item.model_dump(mode="json"))
        try:
            return await asyncio.wait_for(future, self.timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(item.id, None)
            self._emit("approval_resolved", {"id": item.id})

    def resolve(self, approval_id: str, approved: bool) -> bool:
        entry = self._pending.get(approval_id)
        if not entry or entry[1].done():
            return False
        entry[1].set_result(approved)
        return True
