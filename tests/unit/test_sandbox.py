import pytest
from orchestrator.sandbox import (
    SandboxConfig,
    get_sandbox_config,
    MockSandboxClient,
    ExecutionResult,
    SandboxTool,
    get_sandbox_manager,
)


def test_sandbox_config():
    config = SandboxConfig(provider="mock", api_key=None, timeout=30)
    assert config.provider == "mock"
    assert config.timeout == 30


def test_sandbox_config_from_env(monkeypatch):
    monkeypatch.setenv("SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    config = get_sandbox_config()
    assert config.provider == "e2b"
    assert config.api_key == "test_key"


@pytest.mark.asyncio
async def test_mock_client_create():
    client = MockSandboxClient()
    sandbox_id = await client.create_sandbox()
    assert sandbox_id.startswith("mock_sandbox_")


@pytest.mark.asyncio
async def test_mock_client_execute():
    client = MockSandboxClient()
    sandbox_id = await client.create_sandbox()
    
    result = await client.execute_code(sandbox_id, "print('hello world')")
    assert result.success is True
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_mock_client_execute_error():
    client = MockSandboxClient()
    sandbox_id = await client.create_sandbox()
    
    result = await client.execute_code(sandbox_id, "raise Exception('test error')")
    assert result.success is False
    assert "test error" in result.error


@pytest.mark.asyncio
async def test_mock_client_kill():
    client = MockSandboxClient()
    sandbox_id = await client.create_sandbox()
    
    killed = await client.kill_sandbox(sandbox_id)
    assert killed is True
    
    result = await client.execute_code(sandbox_id, "print('test')")
    assert result.success is False


@pytest.mark.asyncio
async def test_sandbox_tool():
    tool = SandboxTool(provider="mock")
    result = await tool.execute(code="print('sandbox test')")
    assert result["success"] is True
    assert "sandbox test" in result["output"]


@pytest.mark.asyncio
async def test_sandbox_tool_error():
    tool = SandboxTool(provider="mock")
    result = await tool.execute(code="1/0")
    assert result["success"] is False
    assert result["error"] is not None


def test_sandbox_manager():
    manager = get_sandbox_manager()
    tool1 = manager.get_tool("test1")
    tool2 = manager.get_tool("test1")
    assert tool1 is tool2