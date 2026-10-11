from __future__ import annotations

import asyncio
import html
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from ..studio import ServerSpec, StudioManager

router = APIRouter(prefix="/studio", tags=["studio"])


def _studio(request: Request) -> StudioManager:
    return request.app.state.studio


class ToggleBody(BaseModel):
    enabled: bool


class ApprovalBody(BaseModel):
    approve: bool


class PickBody(BaseModel):
    task: str


class CallBody(BaseModel):
    qualified: str
    arguments: dict[str, Any] = {}


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    studio = _studio(request)
    scorer = request.app.state.picker.scorer
    servers = studio.states()
    return {
        "servers": len(servers),
        "connected": sum(s.status == "connected" for s in servers),
        "tools": len(studio.tools()),
        "pending_approvals": len(studio.approvals.pending()),
        "jev": {"available": scorer.available(), "model": scorer.model_path.name, "error": scorer.load_error},
    }


@router.get("/servers")
async def list_servers(request: Request) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in _studio(request).states()]


@router.post("/servers", status_code=201)
async def add_server(spec: ServerSpec, request: Request) -> dict[str, Any]:
    try:
        return (await _studio(request).add(spec)).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/servers/{server_id}")
async def update_server(server_id: str, spec: ServerSpec, request: Request) -> dict[str, Any]:
    if spec.id != server_id:
        raise HTTPException(status_code=422, detail="id in body does not match the URL")
    try:
        return (await _studio(request).update(spec)).model_dump(mode="json")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]))


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: str, request: Request) -> None:
    try:
        await _studio(request).remove(server_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]))


@router.post("/servers/{server_id}/enabled")
async def set_enabled(server_id: str, body: ToggleBody, request: Request) -> dict[str, Any]:
    try:
        return (await _studio(request).set_enabled(server_id, body.enabled)).model_dump(mode="json")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]))


@router.post("/servers/{server_id}/reconnect")
async def reconnect(server_id: str, request: Request) -> dict[str, Any]:
    try:
        return (await _studio(request).reconnect(server_id)).model_dump(mode="json")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]))


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    return [t.model_dump(mode="json") | {"needs_approval": t.needs_approval()} for t in _studio(request).tools()]


@router.post("/tools/call")
async def call_tool(body: CallBody, request: Request) -> dict[str, Any]:
    studio = _studio(request)
    tool = studio.find_tool(body.qualified)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"No such tool: {body.qualified}")
    return (await studio.call(tool, body.arguments, source="user")).model_dump(mode="json")


@router.post("/pick")
async def pick(body: PickBody, request: Request) -> dict[str, Any]:
    result = await request.app.state.picker.pick(body.task, _studio(request).tools())
    return result.model_dump(mode="json")


@router.get("/approvals")
async def approvals(request: Request) -> list[dict[str, Any]]:
    return [p.model_dump(mode="json") for p in _studio(request).approvals.pending()]


@router.post("/approvals/{approval_id}")
async def resolve_approval(approval_id: str, body: ApprovalBody, request: Request) -> dict[str, bool]:
    if not _studio(request).approvals.resolve(approval_id, body.approve):
        raise HTTPException(status_code=404, detail="That approval request is no longer pending")
    return {"ok": True}


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    studio = _studio(request)
    queue = studio.subscribe()

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), 15)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            studio.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request, code: str = "", state: str | None = None,
                         error: str | None = None) -> HTMLResponse:
    if error or not code:
        body = f"Sign-in failed: {html.escape(error or 'no code returned')}"
    elif _studio(request).complete_oauth(code, state):
        body = "Signed in. You can close this window and return to Studio."
    else:
        body = "This sign-in link is no longer valid. Start the connection again from Studio."
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>Studio</title>"
        "<body style='font:16px -apple-system,system-ui,sans-serif;display:grid;place-items:center;"
        f"height:100vh;margin:0;color:#1d1d1f'><p>{body}</p>")
