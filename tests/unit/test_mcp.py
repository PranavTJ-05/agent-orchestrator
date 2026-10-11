import pytest
from orchestrator.mcp import (
    MCPManager,
    MCPServerConfig,
    MCPTool,
    MCPToolCall,
    MCPToolResult,
)
from orchestrator.mcp.tool import LocalMCPTool


def test_mcp_types():
    config = MCPServerConfig(name="test", url="npx test-server", transport="stdio")
    assert config.name == "test"
    assert config.transport == "stdio"

    tool = MCPTool(name="echo", description="Echo input", input_schema={}, server_name="test")
    assert tool.name == "echo"
    assert tool.server_name == "test"

    tool_call = MCPToolCall(tool=tool, arguments={"text": "hello"})
    assert tool_call.arguments["text"] == "hello"

    result = MCPToolResult(tool_name="echo", success=True, result="hello")
    assert result.success is True


def test_mcp_manager():
    manager = MCPServerConfig(name="test", url="npx test-server", transport="stdio")
    manager2 = MCPManager()
    manager2.add_server(MCPServerConfig(name="test", url="echo hi", transport="stdio"))
    assert "test" in manager2.list_servers()
    assert manager2.get_server("test") is not None


@pytest.mark.asyncio
async def test_local_mcp_tool():
    async def echo_handler(**kwargs):
        return kwargs.get("text", "no text")

    tool = LocalMCPTool(
        name="echo",
        description="Echo input",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=echo_handler,
    )

    result = await tool.execute(text="hello world")
    assert result == "hello world"


@pytest.mark.asyncio
async def test_local_mcp_tool_no_args():
    async def greet_handler(**kwargs):
        return "Hello!"

    tool = LocalMCPTool(
        name="greet",
        description="Greet",
        input_schema={"type": "object", "properties": {}},
        handler=greet_handler,
    )

    result = await tool.execute()
    assert result == "Hello!"