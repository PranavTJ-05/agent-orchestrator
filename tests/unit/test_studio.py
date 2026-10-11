import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from orchestrator.studio import (ApprovalBroker, ApprovalMode, JevScorer, ServerSpec, StudioManager,
                                 ToolPicker)
from orchestrator.studio import manager as manager_module
from orchestrator.studio.models import REDACTED
from orchestrator.studio.store import ServerStore

DEMO = str(Path(__file__).parent.parent / "fixtures" / "demo_mcp_server.py")
MODEL = Path(__file__).parent.parent.parent / "models" / "Jev-Style-0.8B-Decision-v3-Q4_K_M.gguf"


def demo_spec(**kw) -> ServerSpec:
    base = dict(id="demo", name="Demo", transport="stdio", command=sys.executable, args=[DEMO])
    base.update(kw)
    return ServerSpec(**base)


async def wait_status(mgr: StudioManager, sid: str, want: str, timeout: float = 20) -> None:
    for _ in range(int(timeout / 0.1)):
        if mgr.state(sid).status == want:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"{sid} never reached {want}: {mgr.state(sid)}")


@pytest.fixture
async def mgr(tmp_path):
    m = StudioManager(store=ServerStore(tmp_path / "studio"), approvals=ApprovalBroker(timeout=5))
    await m.start()
    yield m
    await m.stop()


# ---- models & store ---------------------------------------------------------
def test_spec_validation():
    with pytest.raises(ValueError):
        ServerSpec(id="Bad Id", name="x", command="npx")
    with pytest.raises(ValueError):
        ServerSpec(id="a", name="x", transport="stdio")
    with pytest.raises(ValueError):
        ServerSpec(id="a", name="x", transport="http", url="ftp://nope")
    spec = ServerSpec(id="fs", name="Files", command="npx -y @modelcontextprotocol/server-filesystem /tmp")
    assert spec.command == "npx" and spec.args[0] == "-y"


def test_secrets_are_masked_and_restored():
    spec = demo_spec(env={"API_KEY": "secret"}, headers={"Authorization": "Bearer t"})
    masked = spec.redacted()
    assert masked.env["API_KEY"] == REDACTED and masked.headers["Authorization"] == REDACTED
    merged = masked.merge_secrets(spec)
    assert merged.env["API_KEY"] == "secret" and merged.headers["Authorization"] == "Bearer t"


def test_store_roundtrip_and_permissions(tmp_path):
    store = ServerStore(tmp_path / "s")
    store.save([demo_spec(env={"K": "v"})])
    assert store.load()[0].env == {"K": "v"}
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    raw = json.loads(store.path.read_text())
    raw["servers"].append({"id": "BROKEN"})  # a corrupt entry must not lose the good one
    store.path.write_text(json.dumps(raw))
    assert [s.id for s in store.load()] == ["demo"]


# ---- live connection to the demo server ---------------------------------------
@pytest.mark.asyncio
async def test_connect_list_and_call(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    names = {t.name: t for t in mgr.tools()}
    assert set(names) == {"add", "write_note", "slow"}
    assert names["add"].read_only is True and names["add"].qualified == "demo__add"
    result = await mgr.call(names["add"], {"a": 2, "b": 3})
    assert result.ok and result.text.strip() == "5"


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected_without_calling(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    tool = mgr.find_tool("demo__add")
    result = await mgr.call(tool, {"a": "two", "b": 3})
    assert not result.ok and "Invalid arguments" in result.text


@pytest.mark.asyncio
async def test_writing_tools_need_approval(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    tool = mgr.find_tool("demo__write_note")
    assert tool.needs_approval()

    async def approve(item):
        return True
    mgr.approvals.handler = approve
    assert (await mgr.call(tool, {"text": "hi"})).ok

    async def deny(item):
        return False
    mgr.approvals.handler = deny
    denied = await mgr.call(tool, {"text": "hi"})
    assert not denied.ok and "did not approve" in denied.text


@pytest.mark.asyncio
async def test_ui_approval_flow_and_timeout(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    tool = mgr.find_tool("demo__write_note")
    task = asyncio.create_task(mgr.call(tool, {"text": "x"}))
    for _ in range(50):
        if mgr.approvals.pending():
            break
        await asyncio.sleep(0.05)
    pending = mgr.approvals.pending()
    assert len(pending) == 1 and pending[0].tool == "write_note"
    assert mgr.approvals.resolve(pending[0].id, True)
    assert (await task).ok
    mgr.approvals.timeout = 0.3  # nobody answers -> denied
    assert not (await mgr.call(tool, {"text": "y"})).ok


@pytest.mark.asyncio
async def test_policy_modes(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    assert not mgr.find_tool("demo__write_note").needs_approval()
    await mgr.update(demo_spec(approval=ApprovalMode.BLOCK))
    await asyncio.sleep(0.2)
    assert mgr.tools() == []


@pytest.mark.asyncio
async def test_call_timeout(mgr, monkeypatch):
    monkeypatch.setattr(manager_module, "CALL_TIMEOUT", 0.5)
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    result = await mgr.call(mgr.find_tool("demo__slow"), {"seconds": 5})
    assert not result.ok and "timed out" in result.text


@pytest.mark.asyncio
async def test_bad_command_reports_error_and_keeps_retrying(mgr):
    await mgr.add(ServerSpec(id="broken", name="Broken", command="definitely-not-a-real-binary-xyz"))
    await wait_status(mgr, "broken", "error")
    assert mgr.state("broken").error
    assert mgr.tools() == []


@pytest.mark.asyncio
async def test_disable_enable_remove_persist(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    await mgr.set_enabled("demo", False)
    assert mgr.state("demo").status == "disabled" and mgr.tools() == []
    assert mgr.store.load()[0].enabled is False
    await mgr.set_enabled("demo", True)
    await wait_status(mgr, "demo", "connected")
    await mgr.remove("demo")
    assert mgr.store.load() == []
    with pytest.raises(KeyError):
        mgr.state("demo")


@pytest.mark.asyncio
async def test_server_survives_restart_of_manager(tmp_path):
    store = ServerStore(tmp_path / "studio")
    first = StudioManager(store=store)
    await first.start()
    await first.add(demo_spec())
    await wait_status(first, "demo", "connected")
    await first.stop()
    second = StudioManager(store=store)
    await second.start()
    await wait_status(second, "demo", "connected")
    await second.stop()


# ---- picker ----------------------------------------------------------------
class NoModel(JevScorer):
    def available(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_picker_returns_all_when_few_and_keywords_otherwise(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    tools = mgr.tools()
    picker = ToolPicker(NoModel())
    few = await picker.pick("anything", tools, k=4)
    assert few.method == "all" and len(few.tools) == 3
    ranked = await picker.pick("add two numbers", tools, k=1)
    assert ranked.method == "keyword" and ranked.tools[0].name == "add"
    previewed = await picker.pick("add two numbers", tools, k=4, always_rank=True)
    assert previewed.method == "keyword" and len(previewed.tools) == 3  # ranked, not "all"


@pytest.mark.skipif(not MODEL.exists(), reason="Jev model not downloaded")
@pytest.mark.asyncio
async def test_jev_picks_the_right_tool(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    picker = ToolPicker(JevScorer(str(MODEL)))
    result = await picker.pick("what is 17 plus 25?", mgr.tools(), k=1)
    assert result.method == "jev"
    assert result.tools[0].name == "add" and result.tools[0].probability > 0.5
    result = await picker.pick("remember this: buy milk", mgr.tools(), k=1)
    assert result.tools[0].name == "write_note"


# ---- remote transports against a real local server --------------------------
import socket
import subprocess


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def remote_server():
    procs = []

    def start(transport: str):
        port = _free_port()
        proc = subprocess.Popen([sys.executable, DEMO, transport, str(port)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(proc)
        for _ in range(100):  # wait until the port accepts connections
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                return port
            except OSError:
                import time
                time.sleep(0.1)
        raise AssertionError("demo server did not start")

    yield start
    for p in procs:
        p.terminate()
        p.wait(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport,path", [("streamable-http", "/mcp"), ("sse", "/sse")])
async def test_remote_transports(mgr, remote_server, transport, path):
    port = remote_server(transport)
    spec = ServerSpec(id="remote", name="Remote", transport="http" if transport == "streamable-http" else "sse",
                      url=f"http://127.0.0.1:{port}{path}", approval=ApprovalMode.ALLOW)
    await mgr.add(spec)
    await wait_status(mgr, "remote", "connected")
    tool = mgr.find_tool("remote__add")
    assert tool is not None and tool.read_only is True
    result = await mgr.call(tool, {"a": 20, "b": 22})
    assert result.ok and result.text.strip() == "42"


@pytest.mark.asyncio
async def test_unreachable_remote_reports_error(mgr):
    await mgr.add(ServerSpec(id="down", name="Down", transport="http", url="http://127.0.0.1:9/mcp"))
    await wait_status(mgr, "down", "error")
    assert mgr.state("down").error


# ---- OAuth plumbing (the SDK handles the protocol; these cover our storage and callback) ------
@pytest.mark.asyncio
async def test_oauth_token_storage_is_private_and_roundtrips(tmp_path):
    from mcp.shared.auth import OAuthToken
    from orchestrator.studio.connection import FileTokenStorage
    storage = FileTokenStorage(tmp_path / "oauth" / "srv.json")
    assert await storage.get_tokens() is None
    await storage.set_tokens(OAuthToken(access_token="abc", token_type="Bearer", refresh_token="r"))
    again = await storage.get_tokens()
    assert again.access_token == "abc" and again.refresh_token == "r"
    assert stat.S_IMODE(os.stat(storage.path).st_mode) == 0o600


@pytest.mark.asyncio
async def test_oauth_callback_matches_state(tmp_path):
    m = StudioManager(store=ServerStore(tmp_path / "studio"))
    await m.add(ServerSpec(id="o", name="O", transport="http", url="http://127.0.0.1:9/mcp", oauth=True, enabled=False))
    conn = m._conns["o"]
    conn.auth_state = "state-123"
    conn._auth_future = asyncio.get_running_loop().create_future()
    assert not m.complete_oauth("code", "wrong-state")        # a forged callback is ignored
    assert not conn._auth_future.done()
    assert m.complete_oauth("the-code", "state-123")
    assert conn._auth_future.result() == ("the-code", "state-123")
    assert not m.complete_oauth("again", "state-123")         # one-shot
