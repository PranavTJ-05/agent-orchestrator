import json
import asyncio
from typing import Any

from .types import MCPServerConfig, MCPTool, MCPToolCall, MCPToolResult


class MCPClient:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.tools: list[MCPTool] = []
        self._process: asyncio.subprocess.Process | None = None

    async def connect(self) -> list[MCPTool]:
        if self.config.transport == "stdio":
            return await self._connect_stdio()
        elif self.config.transport in ("http", "sse"):
            return await self._connect_http()
        else:
            raise ValueError(f"Unsupported transport: {self.config.transport}")

    async def _connect_stdio(self) -> list[MCPTool]:
        cmd = self.config.url.split()
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.env,
        )
        await self._send_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        await asyncio.sleep(0.5)
        response = await self._read_jsonrpc(timeout=5.0)
        if "error" in response:
            pass
        self.tools = await self._list_tools_stdio()
        return self.tools

    async def _connect_http(self) -> list[MCPTool]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.url,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            ) as resp:
                await resp.json()
        self.tools = await self._list_tools_http()
        return self.tools

    async def _list_tools_stdio(self) -> list[MCPTool]:
        await self._send_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        response = await self._read_jsonrpc()
        tools = []
        for t in response.get("result", {}).get("tools", []):
            tools.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=self.config.name,
            ))
        return tools

    async def _list_tools_http(self) -> list[MCPTool]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.url,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ) as resp:
                data = await resp.json()
        tools = []
        for t in data.get("result", {}).get("tools", []):
            tools.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=self.config.name,
            ))
        return tools

    async def call_tool(self, tool_call: MCPToolCall) -> MCPToolResult:
        if self.config.transport == "stdio":
            return await self._call_tool_stdio(tool_call)
        else:
            return await self._call_tool_http(tool_call)

    async def _call_tool_stdio(self, tool_call: MCPToolCall) -> MCPToolResult:
        await self._send_jsonrpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_call.tool.name,
                "arguments": tool_call.arguments,
            },
        })
        response = await self._read_jsonrpc()
        if "error" in response:
            return MCPToolResult(
                tool_name=tool_call.tool.name,
                success=False,
                result=None,
                error=response["error"].get("message", "Unknown error"),
            )
        return MCPToolResult(
            tool_name=tool_call.tool.name,
            success=True,
            result=response.get("result", {}).get("content", []),
        )

    async def _call_tool_http(self, tool_call: MCPToolCall) -> MCPToolResult:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.url,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": tool_call.tool.name,
                        "arguments": tool_call.arguments,
                    },
                },
            ) as resp:
                response = await resp.json()
        if "error" in response:
            return MCPToolResult(
                tool_name=tool_call.tool.name,
                success=False,
                result=None,
                error=response["error"].get("message", "Unknown error"),
            )
        return MCPToolResult(
            tool_name=tool_call.tool.name,
            success=True,
            result=response.get("result", {}).get("content", []),
        )

    async def _send_jsonrpc(self, msg: dict[str, Any]) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.write(json.dumps(msg).encode() + b"\n")
            await self._process.stdin.drain()

    async def _read_jsonrpc(self, timeout: float = 10.0) -> dict[str, Any]:
        if self._process and self._process.stdout:
            import asyncio
            try:
                line = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
                if not line:
                    return {}
                decoded = line.decode().strip()
                if not decoded:
                    return {}
                return json.loads(decoded)
            except asyncio.TimeoutError:
                return {"error": {"code": -32603, "message": "Request timed out"}}
            except json.JSONDecodeError:
                return {"error": {"code": -32700, "message": "Invalid JSON received"}}
        return {}

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None


class MCPManager:
    def __init__(self):
        self._servers: dict[str, MCPClient] = {}

    def add_server(self, config: MCPServerConfig) -> MCPClient:
        client = MCPClient(config)
        self._servers[config.name] = client
        return client

    def get_server(self, name: str) -> MCPClient | None:
        return self._servers.get(name)

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def get_all_tools(self) -> list[MCPTool]:
        tools = []
        for client in self._servers.values():
            tools.extend(client.tools)
        return tools


__all__ = ["MCPClient", "MCPManager"]