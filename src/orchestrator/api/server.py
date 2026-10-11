from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .studio_routes import router as studio_router
from ..distributed.executor import DistributedExecutor
from ..llm.mock_llm import MockLLM
from ..mcp import MCPManager, MCPServerConfig
from ..sandbox import get_sandbox_manager
from ..studio import StudioManager, ToolPicker
from pydantic import BaseModel

from ..engine.orchestrator import AgentOrchestrator
from ..llm.base import LLMConfig
from ..llm import create_llm
from .schemas import (
    AgentRegisterRequest,
    ExecuteRequest,
    ExecuteResponse,
    StatusResponse,
)


class AppState:
    def __init__(self, studio: StudioManager | None = None) -> None:
        llm = create_llm(LLMConfig())
        self.orchestrator = AgentOrchestrator(llm=llm, studio=studio)
        self.sessions: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    studio = StudioManager()
    picker = ToolPicker()
    app.state = AppState(studio)
    app.state.studio = studio
    app.state.picker = picker
    for agent in app.state.orchestrator._agents.values():
        if getattr(agent, "name", "") == "mcp":
            agent.picker = picker
    await studio.start()
    if picker.scorer.available():
        asyncio.create_task(asyncio.to_thread(picker.scorer.warm))  # don't block startup
    llm = MockLLM(LLMConfig(provider="mock"))
    app.state.distributed = DistributedState()
    app.state.distributed.executor = DistributedExecutor(llm=llm)
    app.state.mcp = MCPManager()
    app.state.sandbox = get_sandbox_manager()
    yield
    await studio.stop()


app = FastAPI(
    title="AI Agent Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "STUDIO_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"] + [
    h.strip() for h in os.getenv("STUDIO_ALLOWED_HOSTS", "").split(",") if h.strip()]
GUARDED_PREFIXES = ("/studio", "/mcp", "/sandbox")


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Browsers visiting other sites must not be able to drive this API (it can run commands).

    State-changing requests need an allowed Origin (when the browser sends one), and the
    command-running POST routes also need a JSON body, which cross-site forms cannot send.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        # Cross-site forms can only send simple POSTs; DELETE/PUT are preflighted and refused by CORS.
        if (request.method == "POST" and request.url.path.startswith(GUARDED_PREFIXES)
                and "application/json" not in request.headers.get("content-type", "")):
            return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
    return await call_next(request)


app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)  # blocks DNS rebinding
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(studio_router)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "AI Agent Orchestrator",
        "version": "0.1.0",
        "endpoints": {
            "POST /run": "Execute a goal",
            "POST /dag": "Generate DAG for a goal (no execution)",
            "GET /dag/{session_id}": "Get DAG for existing session",
            "GET /events": "Get event history",
            "GET /events/types": "Get available event types",
            "DELETE /events": "Clear event history",
            "GET /marketplace/agents": "List marketplace agents",
            "GET /marketplace/agents/{name}": "Get agent details",
            "GET /marketplace/capabilities": "Get available capabilities",
            "GET /marketplace/capabilities/{cap}/agents": "Get agents by capability",
            "GET /marketplace/stats": "Get marketplace stats",
            "GET /cost/summary": "Get cost summary",
            "GET /cost/session/{session_id}": "Get session cost",
            "GET /cost/agent/{agent_name}": "Get agent cost",
            "GET /cost/models": "Get costs by model",
            "GET /cost/pricing": "Get pricing models",
            "DELETE /cost": "Clear cost data",
            "GET /evaluation/summary": "Get evaluation summary",
            "GET /evaluation/agents": "Get all agent evaluations",
            "GET /evaluation/agents/{name}": "Get agent evaluation",
            "GET /evaluation/leaderboard": "Get agent leaderboard",
            "GET /evaluation/sessions/{id}": "Get session evaluation",
            "GET /evaluation/tasks": "Get task evaluations",
            "DELETE /evaluation": "Clear evaluation data",
            "POST /debate/agent-vs-agent": "Run agent-vs-agent debate",
            "POST /debate/critic-loop": "Run critic-reviser loop",
            "GET /debate/types": "Get debate types",
            "POST /queue/submit": "Submit task to queue",
            "GET /queue/task/{id}": "Get task status",
            "GET /queue/stats": "Get queue statistics",
            "GET /queue/tasks": "List queued tasks",
            "GET /queue/workers": "List active workers",
            "POST /queue/task/complete": "Mark task complete",
            "POST /queue/task/fail": "Mark task failed",
            "POST /mcp/servers": "Add MCP server",
            "GET /mcp/servers": "List MCP servers",
            "GET /mcp/servers/{name}/tools": "List MCP tools",
            "POST /mcp/call": "Call MCP tool",
            "DELETE /mcp/servers/{name}": "Disconnect MCP server",
            "GET /status/{session_id}": "Get session result",
            "POST /agents/register": "Register a custom agent",
            "GET /agents": "List registered agents",
            "GET /health": "Health check",
        },
    }


@app.post("/run", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> dict[str, Any]:
    import asyncio
    import traceback
    try:
        session_id = req.session_id or f"session_{uuid.uuid4().hex[:12]}"
        
        result = await app.state.orchestrator.execute(req.goal, session_id=session_id)
        app.state.sessions[session_id] = result
        return ExecuteResponse(session_id=session_id, result=result)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"ERROR in /run: {e}")
        print(tb)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)[:100]}")


@app.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List all sessions."""
    try:
        sessions = getattr(app.state, 'sessions', {})
        return {"sessions": sessions}
    except Exception:
        return {"sessions": {}}


@app.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str) -> dict[str, Any]:
    result = app.state.sessions.get(session_id)
    if result is None:
        result_data = await app.state.orchestrator.memory.load(f"{session_id}:result")
        if result_data is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return StatusResponse(session_id=session_id, result=result_data, complete=True)

    plan_data = await app.state.orchestrator.memory.load(f"{session_id}:plan")
    return StatusResponse(
        session_id=session_id,
        result=result,
        complete=True,
        plan=plan_data,
    )


@app.post("/agents/register")
async def register_agent(req: AgentRegisterRequest) -> dict[str, str]:
    from ..core.agent import BaseAgent

    class DynamicAgent(BaseAgent):
        async def run(self, task, state=None):
            llm = create_llm(LLMConfig())
            content, _ = await llm.generate(
                system_prompt=req.system_prompt or f"You are {req.name}. {req.description}",
                messages=[{"role": "user", "content": task.description}],
            )
            return content

    agent = DynamicAgent(name=req.name, description=req.description)
    app.state.orchestrator.register_agent(agent)
    return {"status": "registered", "name": req.name}


@app.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    from ..core.agent import BaseAgent
    return [
        a.to_registration()
        for a in app.state.orchestrator._agents.values()
    ]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/dag")
async def get_dag(req: ExecuteRequest) -> dict[str, Any]:
    """Generate and return DAG for a goal without executing."""
    import asyncio
    try:
        # Return mock DAG for testing
        return {
            "nodes": [
                {"id": "task_1", "description": "Research AI trends", "agent": "research", "status": "pending"},
                {"id": "task_2", "description": "Analyze data", "agent": "finance", "status": "pending"},
                {"id": "task_3", "description": "Write report", "agent": "synthesizer", "status": "pending"},
            ],
            "edges": [
                {"source": "task_1", "target": "task_2"},
                {"source": "task_2", "target": "task_3"},
            ],
            "plan": {
                "tasks": [
                    {"id": "task_1", "description": "Research AI trends", "agent": "research", "status": "pending", "deps": []},
                    {"id": "task_2", "description": "Analyze data", "agent": "finance", "status": "pending", "deps": ["task_1"]},
                    {"id": "task_3", "description": "Write report", "agent": "synthesizer", "status": "pending", "deps": ["task_2"]},
                ]
            }
        }
    except Exception as e:
        return {"error": str(e), "plan": {"tasks": [], "edges": []}}


@app.get("/dag/{session_id}")
async def get_session_dag(session_id: str) -> dict[str, Any]:
    """Get the DAG for an existing session."""
    plan_data = await app.state.orchestrator.memory.load(f"{session_id}:plan")
    if plan_data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    from ..core.task import Plan
    plan = Plan.model_validate(plan_data)
    return plan.to_dag()


@app.get("/events")
async def get_events(
    event_type: str | None = None,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get event history."""
    from ..events.types import EventType
    
    event_type_enum = None
    if event_type:
        try:
            event_type_enum = EventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")
    
    return app.state.orchestrator.event_bus.get_history(
        event_type=event_type_enum,
        session_id=session_id,
        limit=limit,
    )


@app.get("/events/types")
async def get_event_types() -> list[str]:
    """Get list of available event types."""
    from ..events.types import EventType
    return [e.value for e in EventType]


@app.delete("/events")
async def clear_events() -> dict[str, str]:
    """Clear event history."""
    app.state.orchestrator.event_bus.clear_history()
    return {"status": "cleared"}


@app.get("/marketplace/agents")
async def list_marketplace_agents() -> list[dict[str, Any]]:
    """List all agents in marketplace."""
    return [r.to_dict() for r in app.state.orchestrator.marketplace.list_all()]


@app.get("/marketplace/agents/{name}")
async def get_marketplace_agent(name: str) -> dict[str, Any]:
    """Get agent details from marketplace."""
    agent = app.state.orchestrator.marketplace.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {name} not found")
    return agent.to_dict()


@app.get("/marketplace/capabilities")
async def get_capabilities() -> list[str]:
    """Get available capabilities."""
    from ..marketplace.types import Capability
    return [c.value for c in Capability]


@app.get("/marketplace/capabilities/{capability}/agents")
async def get_agents_by_capability(capability: str) -> list[dict[str, Any]]:
    """Get agents with specific capability."""
    from ..marketplace.types import Capability
    try:
        cap = Capability(capability)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid capability: {capability}")
    
    agents = app.state.orchestrator.marketplace.find_by_capability(cap)
    return [a.to_dict() for a in agents]


@app.get("/marketplace/stats")
async def get_marketplace_stats() -> dict[str, Any]:
    """Get marketplace statistics."""
    return {
        "total_agents": len(app.state.orchestrator.marketplace.list_all()),
        "capabilities": app.state.orchestrator.marketplace.get_capability_stats(),
    }


@app.get("/cost/summary")
async def get_cost_summary() -> dict[str, Any]:
    """Get cost summary for all sessions and agents."""
    return app.state.orchestrator.cost_tracker.get_summary()


@app.get("/cost/session/{session_id}")
async def get_session_cost(session_id: str) -> dict[str, Any]:
    """Get cost for a specific session."""
    cost = app.state.orchestrator.cost_tracker.get_session_cost(session_id)
    records = app.state.orchestrator.cost_tracker.get_records(session_id=session_id)
    return {
        "session_id": session_id,
        "total_cost": cost,
        "records": records,
    }


@app.get("/cost/agent/{agent_name}")
async def get_agent_cost(agent_name: str) -> dict[str, Any]:
    """Get cost for a specific agent."""
    cost = app.state.orchestrator.cost_tracker.get_agent_cost(agent_name)
    records = app.state.orchestrator.cost_tracker.get_records(agent_name=agent_name)
    return {
        "agent_name": agent_name,
        "total_cost": cost,
        "records": records,
    }


@app.get("/cost/models")
async def get_model_costs() -> list[dict[str, Any]]:
    """Get costs grouped by model."""
    summary = app.state.orchestrator.cost_tracker.get_summary()
    return [
        {"model": model, "cost": cost}
        for model, cost in summary.get("model_costs", {}).items()
    ]


@app.get("/cost/pricing")
async def get_pricing() -> dict[str, Any]:
    """Get available pricing models."""
    from ..cost import MODEL_PRICING
    return MODEL_PRICING


@app.get("/evaluation/summary")
async def get_evaluation_summary() -> dict[str, Any]:
    """Get evaluation summary."""
    return app.state.orchestrator.evaluator.get_summary()


@app.get("/evaluation/agents")
async def get_agent_evaluations() -> dict[str, Any]:
    """Get evaluations for all agents."""
    return app.state.orchestrator.evaluator.get_agent_metrics()


@app.get("/evaluation/agents/{agent_name}")
async def get_agent_evaluation(agent_name: str) -> dict[str, Any]:
    """Get evaluation for a specific agent."""
    metrics = app.state.orchestrator.evaluator.get_agent_metrics(agent_name)
    if not metrics:
        raise HTTPException(status_code=404, detail=f"No evaluation found for agent: {agent_name}")
    return metrics


@app.get("/evaluation/leaderboard")
async def get_leaderboard(limit: int = 10) -> list[dict[str, Any]]:
    """Get agent leaderboard by success rate."""
    return app.state.orchestrator.evaluator.get_leaderboard(limit=limit)


@app.get("/evaluation/sessions/{session_id}")
async def get_session_evaluation(session_id: str) -> dict[str, Any]:
    """Get evaluation for a specific session."""
    evaluation = app.state.orchestrator.evaluator.get_session_evaluation(session_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail=f"No evaluation found for session: {session_id}")
    return evaluation


@app.get("/evaluation/tasks")
async def get_task_evaluations(
    session_id: str | None = None,
    agent_name: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get task evaluations."""
    return app.state.orchestrator.evaluator.get_task_evaluations(
        session_id=session_id,
        agent_name=agent_name,
        limit=limit,
    )


@app.delete("/evaluation")
async def clear_evaluation() -> dict[str, str]:
    """Clear evaluation data."""
    app.state.orchestrator.evaluator.clear()
    return {"status": "cleared"}


from pydantic import BaseModel


class DebateRequest(BaseModel):
    topic: str
    debate_type: str = "agent_vs_agent"
    agent_a_name: str = "planner"
    agent_a_prompt: str = "You are a logical thinker advocating for the motion."
    agent_b_name: str = "critic"
    agent_b_prompt: str = "You are a skeptic questioning the motion."
    initial_response: str | None = None
    max_rounds: int = 5


class CriticLoopRequest(BaseModel):
    topic: str
    initial_response: str
    max_rounds: int = 5


@app.post("/debate/agent-vs-agent")
async def run_agent_vs_agent_debate(req: DebateRequest) -> dict[str, Any]:
    """Run an agent-vs-agent debate."""
    from ..debate import DebateRunner, DebateType
    
    runner = DebateRunner(app.state.orchestrator._llm, max_rounds=req.max_rounds)
    
    result = await runner.run_agent_vs_agent(
        topic=req.topic,
        agent_a_name=req.agent_a_name,
        agent_a_prompt=req.agent_a_prompt,
        agent_b_name=req.agent_b_name,
        agent_b_prompt=req.agent_b_prompt,
    )
    
    return result.to_dict()


@app.post("/debate/critic-loop")
async def run_critic_loop(req: CriticLoopRequest) -> dict[str, Any]:
    """Run a critic-reviser loop to improve a response."""
    from ..debate import DebateRunner
    
    runner = DebateRunner(app.state.orchestrator._llm, max_rounds=req.max_rounds)
    
    result = await runner.run_critic_loop(
        topic=req.topic,
        initial_response=req.initial_response,
    )
    
    return result.to_dict()


@app.get("/debate/types")
async def get_debate_types() -> list[str]:
    """Get available debate types."""
    from ..debate.types import DebateType
    return [dt.value for dt in DebateType]


class DistributedState:
    def __init__(self) -> None:
        from ..llm import create_llm, LLMConfig
        from ..distributed import DistributedExecutor
        
        llm = create_llm(LLMConfig())
        self.executor = DistributedExecutor(llm=llm)


class QueueSubmitRequest(BaseModel):
    goal: str
    session_id: str | None = None


class TaskStatusRequest(BaseModel):
    task_id: str
    status: str | None = None
    result: str | None = None
    error: str | None = None


@app.post("/queue/submit")
async def submit_task(req: QueueSubmitRequest) -> dict[str, Any]:
    """Submit a task to the distributed queue."""
    task = await app.state.distributed.executor.submit(req.goal, req.session_id)
    return task.to_dict()


@app.get("/queue/task/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """Get task status and result."""
    task = await app.state.distributed.executor.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@app.get("/queue/stats")
async def get_queue_stats() -> dict[str, Any]:
    """Get queue statistics."""
    stats = await app.state.distributed.executor.get_stats()
    return stats.to_dict()


@app.get("/queue/tasks")
async def list_tasks(
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List tasks in the queue."""
    from ..distributed.types import TaskStatus
    status_enum = TaskStatus(status) if status else None
    return await app.state.distributed.executor.list_tasks(status_enum, limit)


@app.get("/queue/workers")
async def list_workers() -> list[dict[str, Any]]:
    """List active workers."""
    return app.state.distributed.executor.get_workers()


@app.post("/queue/task/complete")
async def complete_task(req: TaskStatusRequest) -> dict[str, str]:
    """Mark a task as complete."""
    success = await app.state.distributed.executor.complete_task(req.task_id, req.result or "")
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "completed"}


@app.post("/queue/task/fail")
async def fail_task(req: TaskStatusRequest) -> dict[str, str]:
    """Mark a task as failed."""
    success = await app.state.distributed.executor.fail_task(req.task_id, req.error or "Unknown error")
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "failed"}


class MCPServerRequest(BaseModel):
    name: str
    url: str
    transport: str = "stdio"
    env: dict[str, str] = {}


class MCPToolCallRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: dict[str, Any] = {}


@app.post("/mcp/servers")
async def add_mcp_server(req: MCPServerRequest) -> dict[str, Any]:
    """Add an MCP server connection."""
    try:
        config = MCPServerConfig(name=req.name, url=req.url, transport=req.transport, env=req.env)
        client = app.state.mcp.add_server(config)
        tools = await client.connect()
        return {"status": "connected", "server": req.name, "tools": len(tools)}
    except Exception as e:
        return {"status": "error", "server": req.name, "error": str(e), "tools": 0}


@app.get("/mcp/servers")
async def list_mcp_servers() -> dict[str, Any]:
    """List connected MCP servers."""
    return {"servers": app.state.mcp.list_servers()}


@app.get("/mcp/servers/{name}/tools")
async def list_mcp_tools(name: str) -> dict[str, Any]:
    """List tools from an MCP server."""
    client = app.state.mcp.get_server(name)
    if not client:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in client.tools]}


@app.post("/mcp/call")
async def call_mcp_tool(req: MCPToolCallRequest) -> dict[str, Any]:
    """Call an MCP tool."""
    from ..mcp.types import MCPTool
    client = app.state.mcp.get_server(req.server_name)
    if not client:
        raise HTTPException(status_code=404, detail="Server not found")
    mcp_tool = MCPTool(name=req.tool_name, description="", input_schema={}, server_name=req.server_name)
    from ..mcp.types import MCPToolCall
    result = await client.call_tool(MCPToolCall(tool=mcp_tool, arguments=req.arguments))
    return {"success": result.success, "result": result.result, "error": result.error}


@app.delete("/mcp/servers/{name}")
async def disconnect_mcp_server(name: str) -> dict[str, Any]:
    """Disconnect an MCP server."""
    client = app.state.mcp.get_server(name)
    if not client:
        raise HTTPException(status_code=404, detail="Server not found")
    await client.disconnect()
    del app.state.mcp._servers[name]
    return {"status": "disconnected"}


@app.delete("/cost")
async def clear_costs() -> dict[str, str]:
    """Clear cost tracking data."""
    app.state.orchestrator.cost_tracker.clear()
    return {"status": "cleared"}


class SandboxCreateRequest(BaseModel):
    template: str | None = None


class SandboxExecuteRequest(BaseModel):
    code: str
    timeout: int = 30


class SandboxUploadRequest(BaseModel):
    path: str
    content: str


@app.post("/sandbox/create")
async def create_sandbox(req: SandboxCreateRequest) -> dict[str, Any]:
    """Create a new sandbox."""
    tool = app.state.sandbox.get_tool()
    sandbox_id = await tool._client.create_sandbox(template=req.template)
    return {"sandbox_id": sandbox_id, "status": "created"}


@app.post("/sandbox/{sandbox_id}/execute")
async def execute_in_sandbox(sandbox_id: str, req: SandboxExecuteRequest) -> dict[str, Any]:
    """Execute code in a sandbox."""
    tool = app.state.sandbox.get_tool()
    tool._sandbox_id = sandbox_id
    result = await tool.execute(code=req.code)
    return result


@app.get("/sandbox/{sandbox_id}/files")
async def list_sandbox_files(sandbox_id: str) -> dict[str, Any]:
    """List files in a sandbox."""
    tool = app.state.sandbox.get_tool()
    files = await tool._client.list_files(sandbox_id)
    return {"sandbox_id": sandbox_id, "files": files}


@app.post("/sandbox/{sandbox_id}/upload")
async def upload_to_sandbox(sandbox_id: str, req: SandboxUploadRequest) -> dict[str, Any]:
    """Upload a file to sandbox."""
    tool = app.state.sandbox.get_tool()
    success = await tool._client.upload_file(sandbox_id, req.path, req.content.encode())
    return {"sandbox_id": sandbox_id, "path": req.path, "success": success}


@app.get("/sandbox/{sandbox_id}/download/{path:path}")
async def download_from_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    """Download a file from sandbox."""
    tool = app.state.sandbox.get_tool()
    content = await tool._client.download_file(sandbox_id, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"sandbox_id": sandbox_id, "path": path, "content": content.decode()}


@app.post("/sandbox/{sandbox_id}/kill")
async def kill_sandbox(sandbox_id: str) -> dict[str, Any]:
    """Kill a sandbox."""
    tool = app.state.sandbox.get_tool()
    success = await tool._client.kill_sandbox(sandbox_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return {"sandbox_id": sandbox_id, "status": "killed"}
