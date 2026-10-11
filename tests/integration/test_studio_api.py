import asyncio
import sys
from pathlib import Path

import httpx
import pytest

DEMO = str(Path(__file__).parent.parent / "fixtures" / "demo_mcp_server.py")
SPEC = {"id": "demo", "name": "Demo", "transport": "stdio", "command": sys.executable, "args": [DEMO]}
JSON = {"Content-Type": "application/json"}


@pytest.fixture(scope="module")
def chroma_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("chroma")  # Chroma allows one in-process client config per run


@pytest.fixture
async def client(tmp_path, monkeypatch, chroma_dir):
    monkeypatch.setenv("STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_EMBEDDING", "hash")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    import importlib
    from orchestrator.studio import store
    importlib.reload(store)  # pick up STUDIO_DIR
    from orchestrator.api import server
    importlib.reload(server)
    async with server.app.router.lifespan_context(server.app):
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8003") as c:
            yield c


async def connected(client, sid="demo"):
    for _ in range(200):
        servers = (await client.get("/studio/servers")).json()
        if any(s["spec"]["id"] == sid and s["status"] == "connected" for s in servers):
            return
        await asyncio.sleep(0.1)
    raise AssertionError("server never connected")


@pytest.mark.asyncio
async def test_server_lifecycle_and_tools(client):
    r = await client.post("/studio/servers", json={**SPEC, "env": {"TOKEN": "s3cret"}}, headers=JSON)
    assert r.status_code == 201
    assert r.json()["spec"]["env"]["TOKEN"] != "s3cret"  # secrets never leave the server
    await connected(client)
    tools = (await client.get("/studio/tools")).json()
    assert {t["name"] for t in tools} == {"add", "write_note", "slow"}
    assert next(t for t in tools if t["name"] == "add")["needs_approval"] is False
    assert next(t for t in tools if t["name"] == "write_note")["needs_approval"] is True
    call = await client.post("/studio/tools/call", json={"qualified": "demo__add", "arguments": {"a": 4, "b": 5}}, headers=JSON)
    assert call.json()["ok"] and call.json()["text"].strip() == "9"
    assert (await client.post("/studio/servers", json=SPEC, headers=JSON)).status_code == 409
    status = (await client.get("/studio/status")).json()
    assert status["connected"] == 1 and status["tools"] == 3
    assert (await client.delete("/studio/servers/demo")).status_code == 204
    assert (await client.get("/studio/servers")).json() == []


@pytest.mark.asyncio
async def test_approval_through_api(client):
    await client.post("/studio/servers", json=SPEC, headers=JSON)
    await connected(client)
    call = asyncio.create_task(client.post(
        "/studio/tools/call", json={"qualified": "demo__write_note", "arguments": {"text": "hi"}}, headers=JSON))
    for _ in range(100):
        pending = (await client.get("/studio/approvals")).json()
        if pending:
            break
        await asyncio.sleep(0.05)
    assert pending[0]["tool"] == "write_note"
    assert (await client.post(f"/studio/approvals/{pending[0]['id']}", json={"approve": True}, headers=JSON)).status_code == 200
    assert (await call).json()["ok"] is True
    assert (await client.post("/studio/approvals/nope", json={"approve": True}, headers=JSON)).status_code == 404


@pytest.mark.asyncio
async def test_pick_endpoint(client):
    await client.post("/studio/servers", json=SPEC, headers=JSON)
    await connected(client)
    r = (await client.post("/studio/pick", json={"task": "add 2 and 3"}, headers=JSON)).json()
    assert r["tools"] and r["method"] in {"jev", "keyword", "all"}


@pytest.mark.asyncio
async def test_cross_site_requests_are_blocked(client):
    evil = {**JSON, "Origin": "https://evil.example"}
    assert (await client.post("/studio/servers", json=SPEC, headers=evil)).status_code == 403
    form = {"Content-Type": "text/plain"}
    assert (await client.post("/studio/servers", content="{}", headers=form)).status_code == 415
    ok = {**JSON, "Origin": "http://localhost:3000"}
    assert (await client.get("/studio/servers", headers=ok)).status_code == 200
    rebound = await client.get("/studio/servers", headers={"Host": "attacker.example"})
    assert rebound.status_code == 400  # DNS rebinding


@pytest.mark.asyncio
async def test_validation_errors(client):
    bad = await client.post("/studio/servers", json={"id": "x", "name": "x", "transport": "stdio"}, headers=JSON)
    assert bad.status_code == 422
    assert (await client.delete("/studio/servers/ghost")).status_code == 404
    assert (await client.post("/studio/tools/call", json={"qualified": "ghost__x"}, headers=JSON)).status_code == 404
