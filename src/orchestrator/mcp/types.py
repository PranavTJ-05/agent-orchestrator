from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPServerConfig:
    name: str
    url: str
    transport: str = "stdio"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


@dataclass
class MCPToolCall:
    tool: MCPTool
    arguments: dict[str, Any]


@dataclass
class MCPToolResult:
    tool_name: str
    success: bool
    result: Any
    error: str | None = None


__all__ = [
    "MCPServerConfig",
    "MCPTool",
    "MCPToolCall",
    "MCPToolResult",
]