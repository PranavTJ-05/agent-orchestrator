from typing import Any
from ..core.tool import Tool
from .e2b_client import create_sandbox_client, ExecutionResult
from .config import get_sandbox_config


class SandboxTool(Tool):
    def __init__(self, provider: str | None = None, api_key: str | None = None, template: str | None = None):
        config = get_sandbox_config()
        self._provider = provider or config.provider
        self._api_key = api_key or config.api_key
        self._template = template or config.template
        self._client = create_sandbox_client(
            provider=self._provider,
            api_key=self._api_key,
            template=self._template
        )
        self._sandbox_id: str | None = None
        
        super().__init__(
            name="sandbox_execute",
            description="Execute Python code in a secure sandbox. Use this for running Python code, data analysis, or any computation. Returns stdout output and any errors.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute in the sandbox"
                    }
                },
                "required": ["code"]
            }
        )

    async def execute(self, **kwargs: Any) -> Any:
        code = kwargs.get("code", "")
        if not code:
            return {"success": False, "error": "No code provided"}

        if not self._sandbox_id:
            self._sandbox_id = await self._client.create_sandbox()

        result: ExecutionResult = await self._client.execute_code(
            self._sandbox_id, 
            code,
            timeout=30
        )

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "logs": result.logs,
            "sandbox_id": self._sandbox_id
        }

    async def reset_sandbox(self) -> None:
        if self._sandbox_id:
            await self._client.kill_sandbox(self._sandbox_id)
            self._sandbox_id = None
        self._sandbox_id = await self._client.create_sandbox()


class SandboxManager:
    def __init__(self):
        config = get_sandbox_config()
        self._provider = config.provider
        self._api_key = config.api_key
        self._template = config.template
        self._tools: dict[str, SandboxTool] = {}

    def get_tool(self, name: str = "default") -> SandboxTool:
        if name not in self._tools:
            self._tools[name] = SandboxTool(
                provider=self._provider,
                api_key=self._api_key,
                template=self._template
            )
        return self._tools[name]

    async def kill_all(self) -> None:
        for tool in self._tools.values():
            await tool.reset_sandbox()
        self._tools.clear()


_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager


__all__ = ["SandboxTool", "SandboxManager", "get_sandbox_manager"]