from typing import Any

from ..core.tool import Tool
from .client import MCPManager
from .types import MCPTool


class MCPServerTool(Tool):
    def __init__(self, mcp_tool: MCPTool, manager: MCPManager):
        super().__init__(
            name=f"{mcp_tool.server_name}:{mcp_tool.name}",
            description=mcp_tool.description,
            parameters=mcp_tool.input_schema.get("properties", {}),
        )
        self._mcp_tool = mcp_tool
        self._manager = manager

    async def execute(self, **kwargs: Any) -> Any:
        from .types import MCPToolCall
        client = self._manager.get_server(self._mcp_tool.server_name)
        if not client:
            raise ValueError(f"MCP server {self._mcp_tool.server_name} not connected")
        tool_call = MCPToolCall(tool=self._mcp_tool, arguments=kwargs)
        result = await client.call_tool(tool_call)
        if not result.success:
            raise RuntimeError(f"MCP tool failed: {result.error}")
        return result.result


class LocalMCPTool(Tool):
    def __init__(self, name: str, description: str, input_schema: dict[str, Any], handler):
        super().__init__(
            name=name,
            description=description,
            parameters=input_schema.get("properties", {}),
        )
        self._handler = handler
        self._input_schema = input_schema

    async def execute(self, **kwargs: Any) -> Any:
        return await self._handler(**kwargs)


__all__ = ["MCPServerTool", "LocalMCPTool"]