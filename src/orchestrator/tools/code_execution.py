from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from ..core.tool import Tool
from ..sandbox import get_sandbox_config, SandboxTool, SelfHealingExecutor


class PythonExecutionTool(Tool):
    def __init__(self) -> None:
        config = get_sandbox_config()
        self._use_sandbox = config.provider == "e2b" and config.api_key
        self._sandbox_tool = SandboxTool() if self._use_sandbox else None
        self._self_healer = SelfHealingExecutor(self._sandbox_tool or self)
        
        super().__init__(
            name="python_execute",
            description="Execute Python code and return the output. Use this for calculations, data processing, and running scripts. The tool automatically retries and fixes common errors.",
        )

    async def execute(self, code: str) -> str:
        if self._use_sandbox and self._sandbox_tool:
            result = await self._sandbox_tool.execute(code=code)
            if result.get("success"):
                output = result.get("output", "")
                error = result.get("error")
                if error:
                    return f"Error:\n{error}\n\nOutput:\n{output}"
                return output or "Code executed successfully (no output)"
            return f"Error: {result.get('error', 'Unknown error')}"
        
        return await self._execute_local(code)

    async def execute_with_healing(self, code: str, llm=None) -> str:
        """Execute code with automatic error fixing."""
        if self._use_sandbox and self._sandbox_tool:
            healer = SelfHealingExecutor(self._sandbox_tool, llm)
            result = await healer.execute_with_healing(code)
            if result["success"]:
                attempts = result["attempts"]
                output = result["output"]
                if attempts > 1:
                    return f"[Self-healed after {attempts} attempts]\n{output}"
                return output
            else:
                return f"Error after {result['attempts']} attempts:\n{result['error']}"
        
        result = await self._execute_local(code)
        if result.startswith("Error"):
            return f"[Self-healing not available for local execution]\n{result}"
        return result

    async def _execute_local(self, code: str) -> str:
        """Execute Python code and capture stdout, stderr, and return value."""
        # Security: Only allow safe operations
        # Block dangerous imports and operations
        forbidden_patterns = [
            'import os', 'import subprocess', 'import sys',
            '__import__', 'eval(', 'exec(', 'compile(',
            'open(', 'file(', 'input(', 'exit(', 'quit(',
            'globals()', 'locals()', 'vars()', 'getattr(',
            'setattr(', 'delattr(', 'hasattr(',
            'shutil', 'socket', 'urllib', 'requests',
        ]
        
        # Check for forbidden patterns
        for pattern in forbidden_patterns:
            if pattern in code:
                return f"Error: Forbidden pattern detected: {pattern}"
        
        # Capture stdout and stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            # Execute the code with restricted globals
            # Only allow basic builtins and safe modules
            safe_globals = {
                '__builtins__': {
                    'print': print, 'len': len, 'str': str, 'int': int, 'float': float,
                    'bool': bool, 'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                    'range': range, 'enumerate': enumerate, 'zip': zip, 'sorted': sorted,
                    'reversed': reversed, 'sum': sum, 'min': min, 'max': max, 'abs': abs,
                    'round': round, 'pow': pow, 'divmod': divmod, 'all': all, 'any': any,
                    'isinstance': isinstance, 'issubclass': issubclass, 'hash': hash,
                    'type': type, 'repr': repr, 'format': format, 'input': input,
                },
                'math': __import__('math'),
                'random': __import__('random'),
                'datetime': __import__('datetime'),
                'json': __import__('json'),
            }
            
            safe_locals = {}
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Execute the code
                exec(code, safe_globals, safe_locals)
            
            stdout_result = stdout_capture.getvalue()
            stderr_result = stderr_capture.getvalue()
            
            # Format the output
            output_parts = []
            if stdout_result.strip():
                output_parts.append("Output:\n" + stdout_result.rstrip())
            if stderr_result.strip():
                output_parts.append("Errors:\n" + stderr_result.rstrip())
            
            if not output_parts:
                output_parts.append("Code executed successfully (no output)")
            
            return "\n\n".join(output_parts)
            
        except Exception as e:
            return f"Error executing Python code:\n{traceback.format_exc()}"