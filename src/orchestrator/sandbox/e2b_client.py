from dataclasses import dataclass
from typing import Any
import os


@dataclass
class ExecutionResult:
    success: bool
    output: str
    error: str | None = None
    logs: str | None = None


class E2BClient:
    def __init__(self, api_key: str | None = None, template: str | None = None):
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.template = template
        self._sandboxes: dict[str, Any] = {}

    async def create_sandbox(self, template: str | None = None) -> str:
        if not self.api_key:
            raise ValueError("E2B_API_KEY not set")

        from e2b import Sandbox
        
        if template:
            sandbox = Sandbox.create(template=template, api_key=self.api_key)
        else:
            sandbox = Sandbox.create(api_key=self.api_key)
        
        sandbox_id = sandbox.sandbox_id
        self._sandboxes[sandbox_id] = sandbox
        return sandbox_id

    async def execute_code(self, sandbox_id: str, code: str, timeout: int = 30) -> ExecutionResult:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Sandbox {sandbox_id} not found"
            )

        try:
            python_code = f'python -c "{code.replace('"', '\\"')}"'
            result = sandbox.commands.run(python_code, timeout=timeout)
            return ExecutionResult(
                success=result.exit_code == 0,
                output=result.stdout,
                error=result.stderr if result.exit_code != 0 else None,
                logs=result.stderr
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e)
            )

    async def upload_file(self, sandbox_id: str, path: str, content: bytes) -> bool:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False
        
        try:
            sandbox.files.write(path, content)
            return True
        except Exception:
            return False

    async def download_file(self, sandbox_id: str, path: str) -> bytes | None:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return None
        
        try:
            return sandbox.files.read(path)
        except Exception:
            return None

    async def list_files(self, sandbox_id: str) -> list[str]:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return []
        
        try:
            return sandbox.files.list()
        except Exception:
            return []

    async def kill_sandbox(self, sandbox_id: str) -> bool:
        sandbox = self._sandboxes.pop(sandbox_id, None)
        if not sandbox:
            return False
        
        try:
            sandbox.kill()
            return True
        except Exception:
            return False

    async def kill_all(self) -> None:
        for sandbox in list(self._sandboxes.values()):
            try:
                sandbox.kill()
            except Exception:
                pass
        self._sandboxes.clear()


class MockSandboxClient:
    """Mock sandbox client for testing without API costs."""
    
    def __init__(self, api_key: str | None = None, template: str | None = None):
        self._sandboxes: dict[str, dict] = {}
        self._counter = 0

    async def create_sandbox(self, template: str | None = None) -> str:
        self._counter += 1
        sandbox_id = f"mock_sandbox_{self._counter}"
        self._sandboxes[sandbox_id] = {
            "files": {},
            "created_at": __import__("datetime").datetime.now()
        }
        return sandbox_id

    async def execute_code(self, sandbox_id: str, code: str, timeout: int = 30) -> ExecutionResult:
        if sandbox_id not in self._sandboxes:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Sandbox {sandbox_id} not found"
            )

        try:
            import sys
            from io import StringIO
            
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            try:
                exec(code, {"__builtins__": __builtins__})
            except Exception as e:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                return ExecutionResult(
                    success=False,
                    output=stdout_capture.getvalue(),
                    error=str(e)
                )
            
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            return ExecutionResult(
                success=True,
                output=stdout_capture.getvalue(),
                logs=stderr_capture.getvalue() if stderr_capture.getvalue() else None
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e)
            )

    async def upload_file(self, sandbox_id: str, path: str, content: bytes) -> bool:
        if sandbox_id not in self._sandboxes:
            return False
        self._sandboxes[sandbox_id]["files"][path] = content
        return True

    async def download_file(self, sandbox_id: str, path: str) -> bytes | None:
        if sandbox_id not in self._sandboxes:
            return None
        return self._sandboxes[sandbox_id]["files"].get(path)

    async def list_files(self, sandbox_id: str) -> list[str]:
        if sandbox_id not in self._sandboxes:
            return []
        return list(self._sandboxes[sandbox_id]["files"].keys())

    async def kill_sandbox(self, sandbox_id: str) -> bool:
        if sandbox_id in self._sandboxes:
            del self._sandboxes[sandbox_id]
            return True
        return False

    async def kill_all(self) -> None:
        self._sandboxes.clear()


def create_sandbox_client(provider: str = "mock", api_key: str | None = None, template: str | None = None):
    if provider == "e2b":
        return E2BClient(api_key=api_key, template=template)
    return MockSandboxClient(api_key=api_key, template=template)


__all__ = ["E2BClient", "MockSandboxClient", "ExecutionResult", "create_sandbox_client"]