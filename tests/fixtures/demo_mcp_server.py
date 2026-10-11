"""Tiny MCP server used by the Studio tests: one read-only tool, one writing tool, one slow tool."""
import asyncio
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("demo")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
def write_note(text: str) -> str:
    """Save a note to disk (simulated)."""
    return f"saved: {text}"


@mcp.tool()
async def slow(seconds: float = 5) -> str:
    """Sleep for a number of seconds, then return."""
    await asyncio.sleep(seconds)
    return "done"


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport != "stdio":
        mcp.settings.port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    mcp.run(transport=transport)
