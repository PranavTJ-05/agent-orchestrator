import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from orchestrator.studio import (ApprovalBroker, ApprovalMode, JevScorer, ServerSpec, StudioManager, ToolInfo,
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
    assert not denied.ok and "declined" in denied.text and "NOT run" in denied.text


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


# ---- agent safety: no repeated side effects, dependency results ---------------------------
from orchestrator.core.state import ExecutionState
from orchestrator.core.task import TaskNode, TaskStatus
from orchestrator.studio import McpAgent


class ScriptedLLM:
    """Returns scripted (content, tool_calls) turns; an Exception instance is raised instead."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen_messages = []
        self.seen_systems = []

    async def generate(self, system_prompt, messages=None, tools=None, tool_choice=None, **kw):
        self.seen_messages.append(messages)
        self.seen_systems.append(system_prompt)
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def tool_call(name, args, call_id="c1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


async def started_count(mgr, queue, tool_name):
    n = 0
    while not queue.empty():
        ev = queue.get_nowait()
        n += ev["type"] == "tool_started" and ev["tool"] == tool_name
    return n


@pytest.mark.asyncio
async def test_failure_after_a_tool_ran_does_not_trigger_a_retry(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    queue = mgr.subscribe()
    llm = ScriptedLLM([("", [tool_call("demo__write_note", {"text": "x"})]), RuntimeError("rate limited")])
    agent = McpAgent(llm, mgr, ToolPicker(NoModel()))
    result = await agent.run(TaskNode(id="t1", description="save a note"))  # must not raise
    assert "Stopped early" in result and "demo.write_note" in result
    assert await started_count(mgr, queue, "write_note") == 1


@pytest.mark.asyncio
async def test_failure_before_any_tool_still_raises_so_retry_is_safe(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    agent = McpAgent(ScriptedLLM([RuntimeError("boom")]), mgr, ToolPicker(NoModel()))
    with pytest.raises(RuntimeError):
        await agent.run(TaskNode(id="t1", description="save a note"))


@pytest.mark.asyncio
async def test_results_of_dependencies_reach_the_agent(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    state = ExecutionState(session_id="s", goal="g", tasks=[
        TaskNode(id="t1", description="add 17 and 25", status=TaskStatus.COMPLETED, result="The sum is 42"),
        TaskNode(id="t2", description="save the sum as a note", deps=["t1"]),
    ])
    llm = ScriptedLLM([("done", [])])
    agent = McpAgent(llm, mgr, ToolPicker(NoModel()))
    await agent.run(state.tasks[1], state)
    first_message = llm.seen_messages[0][0]["content"]
    assert "save the sum as a note" in first_message and "The sum is 42" in first_message


@pytest.mark.asyncio
async def test_malformed_server_schema_does_not_break_calls(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    tool = mgr.find_tool("demo__add").model_copy(update={"input_schema": {"type": "not-a-real-type"}})
    result = await mgr.call(tool, {"a": 1, "b": 2})
    assert result.ok and result.text.strip() == "3"


# ---- planner guidance and honest synthesis -------------------------------------------------
@pytest.mark.asyncio
async def test_planner_is_told_mcp_owns_file_and_data_actions(mgr):
    await mgr.add(demo_spec())
    await wait_status(mgr, "demo", "connected")
    hint = mgr.planner_hint()
    assert "demo" in hint and "write only produces text" in hint


@pytest.mark.asyncio
async def test_write_task_uses_its_own_description_and_dependency_results():
    from orchestrator.agents.synthesizer import SynthesizerAgent, SYNTHESIZER_SYSTEM_PROMPT
    llm = ScriptedLLM([("summary", [])])
    state = ExecutionState(session_id="s", goal="read notes then save a summary", tasks=[
        TaskNode(id="t1", description="read notes.txt", status=TaskStatus.COMPLETED, result="Revenue grew 12 percent"),
        TaskNode(id="t2", description="draft a one-line summary", deps=["t1"]),
    ])
    await SynthesizerAgent(llm).run(state.tasks[1], state)
    prompt = llm.seen_messages[0][0]["content"]
    assert "draft a one-line summary" in prompt and "Revenue grew 12 percent" in prompt
    assert "never claim an action" in SYNTHESIZER_SYSTEM_PROMPT


# ---- routing: a task that names a connected server goes to mcp -------------------------------
@pytest.mark.asyncio
async def test_task_naming_a_connected_server_routes_to_mcp(mgr):
    from orchestrator.agents.router import RouterAgent
    await mgr.add(demo_spec(id="eraser", name="Eraser"))
    await wait_status(mgr, "eraser", "connected")
    assert mgr.mentions_server("Create the file in the Eraser tool and insert the diagram")
    assert not mgr.mentions_server("Write a python function that sorts a list")
    assert not mgr.mentions_server("Erasers are useful")            # whole words only

    class Fake:
        def __init__(self, name):
            self.name, self.description, self.tools = name, "", []
    router = RouterAgent(RecordingLLM(LLMConfig(provider="mock")) if False else None)
    router.register_agents([Fake("coding"), Fake("mcp")])
    router.mcp_matcher = mgr.mentions_server
    assert await router.select(TaskNode(id="t", description="Create a file in Eraser", agent="code")) == "mcp"
    assert await router.select(TaskNode(id="t", description="Sort a list", agent="code")) == "coding"


@pytest.mark.asyncio
async def test_generic_server_names_do_not_hijack_routing(mgr):
    await mgr.add(demo_spec(id="files", name="Files"))
    await wait_status(mgr, "files", "connected")
    assert not mgr.mentions_server("List the files in the folder")  # too generic to imply the server


# ---- duplicate-safe writes and progress-aware tool picking -----------------------------------
@pytest.mark.asyncio
async def test_identical_write_is_not_repeated_in_one_task(mgr):
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    queue = mgr.subscribe()
    call = tool_call("demo__write_note", {"text": "same"})
    llm = ScriptedLLM([("", [call]), ("", [{**call, "id": "c2"}]), ("done", [])])
    result = await McpAgent(llm, mgr, ToolPicker(NoModel())).run(TaskNode(id="t", description="save a note"))
    assert result == "done"
    assert await started_count(mgr, queue, "write_note") == 1   # second identical call short-circuited
    assert "NOT repeated" in json.dumps(llm.seen_messages[2])


@pytest.mark.asyncio
async def test_timeout_message_warns_the_write_may_have_succeeded(mgr, monkeypatch):
    monkeypatch.setattr(manager_module, "CALL_TIMEOUT", 0.4)
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    result = await mgr.call(mgr.find_tool("demo__slow"), {"seconds": 3})
    assert result.timed_out and "do NOT repeat" in result.text


@pytest.mark.asyncio
async def test_find_tools_lets_the_model_pull_in_a_missing_capability(mgr):
    from orchestrator.studio.picker import PickedTool, PickResult

    class FakePicker:
        def __init__(self):
            self.calls = []
        def keyword_pick(self, task, tools, k=3):
            return PickResult(tools=[], method="keyword", confidence=0.0, low_confidence=True, ms=0)

        async def pick(self, task, tools, k=4, always_rank=False):
            self.calls.append((task, [t.qualified for t in tools]))
            names = ["demo__write_note"] if "save" in task else ["demo__add"]
            return PickResult(tools=[PickedTool(qualified=n, server_id="demo", name=n.split("__")[1], probability=1.0) for n in names],
                              method="jev", confidence=1.0, low_confidence=False, ms=0)
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    queue = mgr.subscribe()
    picker = FakePicker()
    llm = ScriptedLLM([
        ("", [tool_call("demo__add", {"a": 1, "b": 2}, "c1")]),
        ("", [tool_call("find_tools", {"need": "save the result somewhere"}, "c2")]),
        ("", [tool_call("demo__write_note", {"text": "3"}, "c3")]),
        ("all done", []),
    ])
    result = await McpAgent(llm, mgr, picker).run(TaskNode(id="t", description="add then keep the answer"))
    assert result == "all done"
    assert await started_count(mgr, queue, "write_note") == 1
    assert any("save the result" in c[0] for c in picker.calls)


@pytest.mark.asyncio
async def test_advanced_twins_are_ranked_after_the_friendly_tool(mgr):
    from orchestrator.studio.picker import _is_advanced
    friendly = ToolInfo(server_id="s", name="create_diagram", qualified="s__create_diagram",
                        description="PREFERRED for creating a diagram from a natural-language prompt")
    advanced = ToolInfo(server_id="s", name="manually_create_diagram", qualified="s__manually_create_diagram",
                        description="ADVANCED - most callers should use create_diagram instead")
    assert _is_advanced(advanced) and not _is_advanced(friendly)
    out = ToolPicker._result([(advanced, 0.6), (friendly, 0.4)], "jev", 0.6, 0.0)
    assert [t.name for t in out.tools] == ["create_diagram", "manually_create_diagram"]


def test_keyword_lookup_prefers_tool_names_and_plurals():
    names = {"list_files": "List files in the team workspace, optionally scoped to a folder.",
             "create_diagram": "PREFERRED for creating a diagram from a natural-language prompt with the file id and app architecture",
             "get_file": "Fetch a file's metadata, document outline, and the list of diagrams in it."}
    tools = [ToolInfo(server_id="e", name=n, qualified="e__" + n, description=d) for n, d in names.items()]
    result = ToolPicker(NoModel()).keyword_pick("list files to find the file id of 'Simple Web App Architecture'", tools, 3)
    assert result.tools[0].name == "list_files" and result.tools[0].probability >= 0.15


@pytest.mark.asyncio
async def test_servers_recommended_twin_joins_the_shortlist(mgr):
    from orchestrator.studio.picker import PickedTool, PickResult
    friendly = ToolInfo(server_id="demo", name="add", qualified="demo__add", description="PREFERRED way to add numbers")
    advanced = ToolInfo(server_id="demo", name="write_note", qualified="demo__write_note",
                        description="ADVANCED - most callers should use add instead")
    candidates = {advanced.qualified: advanced}
    McpAgent._add_recommended_twins(candidates, [friendly, advanced])
    assert list(candidates) == ["demo__write_note", "demo__add"]


# ---- health checks: a server that does not implement ping is still alive --------------------------
@pytest.mark.asyncio
async def test_ping_method_not_found_means_alive_but_transport_errors_do_not():
    from mcp import types as mcp_types
    from mcp.shared.exceptions import McpError
    from orchestrator.studio.connection import ServerConnection

    class NoPing:
        async def send_ping(self):
            raise McpError(mcp_types.ErrorData(code=mcp_types.METHOD_NOT_FOUND, message="Method not found"))

    class Closed:
        async def send_ping(self):
            raise McpError(mcp_types.ErrorData(code=mcp_types.CONNECTION_CLOSED, message="Connection closed"))

    await ServerConnection._ping(NoPing())              # must not raise
    with pytest.raises(McpError):
        await ServerConnection._ping(Closed())          # real failure -> caller reconnects


@pytest.mark.asyncio
async def test_uncertain_pick_lists_other_tools_and_find_tools_accepts_a_name(mgr):
    from orchestrator.studio.picker import PickedTool, PickResult

    class WrongPicker:
        def keyword_pick(self, task, tools, k=3):
            return PickResult(tools=[], method="keyword", confidence=0.0, low_confidence=True, ms=0)

        async def pick(self, task, tools, k=4, always_rank=False):
            return PickResult(tools=[PickedTool(qualified="demo__add", server_id="demo", name="add", probability=0.1)],
                              method="jev", confidence=0.1, low_confidence=True, ms=0)
    await mgr.add(demo_spec(approval=ApprovalMode.ALLOW))
    await wait_status(mgr, "demo", "connected")
    queue = mgr.subscribe()
    llm = ScriptedLLM([
        ("", [tool_call("find_tools", {"need": "demo__write_note"}, "c1")]),
        ("", [tool_call("demo__write_note", {"text": "hi"}, "c2")]),
        ("saved", []),
    ])
    result = await McpAgent(llm, mgr, WrongPicker()).run(TaskNode(id="t", description="draw my architecture"))
    assert result == "saved"
    assert "demo__write_note" in llm.seen_systems[0]   # shown by name because the pick was uncertain
    assert await started_count(mgr, queue, "write_note") == 1
