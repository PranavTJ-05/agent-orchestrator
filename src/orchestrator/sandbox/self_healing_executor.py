from typing import Any
from .e2b_client import ExecutionResult
from .self_healing import ErrorClassifier, ErrorInfo


class SelfHealingExecutor:
    MAX_RETRIES = 3

    def __init__(self, code_executor, llm=None):
        self._code_executor = code_executor
        self._llm = llm
        self._retry_history: dict[str, list[dict]] = {}

    async def execute_with_healing(
        self, 
        code: str, 
        sandbox_id: str | None = None,
        context: str = ""
    ) -> dict[str, Any]:
        retry_count = 0
        current_code = code

        while retry_count < self.MAX_RETRIES:
            result = await self._execute_code(current_code, sandbox_id)

            if result.success:
                return {
                    "success": True,
                    "output": result.output,
                    "attempts": retry_count + 1,
                    "original_code": code,
                    "final_code": current_code,
                    "error": None,
                }

            error_info = ErrorClassifier.classify(result.error or "Unknown error")

            if retry_count == 0:
                self._retry_history[code] = []

            self._retry_history[code].append({
                "attempt": retry_count + 1,
                "error": result.error,
                "error_type": error_info.error_type.value,
                "fix_suggestion": error_info.fix_suggestion,
            })

            if self._llm:
                fixed_code = await self._fix_code(
                    current_code, 
                    result.error, 
                    error_info,
                    context
                )
                if fixed_code and fixed_code != current_code:
                    current_code = fixed_code
                else:
                    break
            else:
                break

            retry_count += 1

        return {
            "success": False,
            "output": "",
            "attempts": retry_count + 1,
            "original_code": code,
            "final_code": current_code,
            "error": result.error if retry_count > 0 else None,
            "retry_history": self._retry_history.get(code, []),
        }

    async def _execute_code(self, code: str, sandbox_id: str | None = None) -> ExecutionResult:
        if hasattr(self._code_executor, '_client'):
            if sandbox_id:
                self._code_executor._sandbox_id = sandbox_id
            result = await self._code_executor.execute(code=code)
            return ExecutionResult(
                success=result.get('success', False),
                output=result.get('output', ''),
                error=result.get('error')
            )
        elif hasattr(self._code_executor, 'execute'):
            exec_result = await self._code_executor.execute(code)
            if isinstance(exec_result, str):
                is_error = exec_result.startswith("Error:")
                return ExecutionResult(
                    success=not is_error,
                    output="" if is_error else exec_result,
                    error=exec_result if is_error else None
                )
            return ExecutionResult(success=True, output=str(exec_result))
        else:
            return ExecutionResult(
                success=False,
                output="",
                error="Invalid code executor"
            )

    async def _fix_code(
        self, 
        code: str, 
        error: str, 
        error_info: ErrorInfo,
        context: str
    ) -> str | None:
        if not self._llm:
            return None

        fix_prompt = f"""You are a code debugger. Fix the following Python code that has an error.

Error Type: {error_info.error_type.value}
Error Message: {error}
Fix Suggestion: {error_info.fix_suggestion}

Context: {context or 'No additional context'}

Original Code:
```python
{code}
```

Fixed Code (only output the fixed Python code, no explanations):
```python
"""

        try:
            content, _ = await self._llm.generate(
                system_prompt="You are an expert Python programmer.",
                messages=[{"role": "user", "content": fix_prompt}],
            )

            if '```python' in content:
                start = content.find('```python') + 9
                end = content.find('```', start)
                if end > start:
                    return content[start:end].strip()

            return content.strip() if content else None
        except Exception:
            return None


__all__ = ["SelfHealingExecutor"]