from __future__ import annotations

from typing import Any

from .base import LLM, LLMConfig, LLMUsage


MOCK_RESPONSES = {
    "plan": '{"tasks": [{"id": "t1", "description": "Print hello", "agent": "coding", "status": "pending"}]}',
    "route": "coding",
    "synthesize": "Task completed successfully.",
    "research": "Based on research, here is the information you requested.",
    "default": "Task executed successfully.",
}


class MockLLM(LLM):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig(provider="mock", model="mock")
        self._usage = LLMUsage(prompt_tokens=100, completion_tokens=50)
        self._call_count = 0

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        self._call_count += 1
        
        user_msg = ""
        if messages:
            user_msg = messages[-1].get("content", "").lower()
        
        content = MOCK_RESPONSES.get("default", "Mock response")
        
        if "plan" in system_prompt.lower() or "goal" in user_msg:
            content = MOCK_RESPONSES.get("plan", MOCK_RESPONSES["default"])
        elif "route" in system_prompt.lower() or "select" in system_prompt.lower():
            content = MOCK_RESPONSES.get("route", "coding")
        elif "synthesiz" in system_prompt.lower():
            content = MOCK_RESPONSES.get("synthesize", MOCK_RESPONSES["default"])
        elif "research" in user_msg:
            content = MOCK_RESPONSES.get("research", MOCK_RESPONSES["default"])
        
        self._usage = LLMUsage(prompt_tokens=100, completion_tokens=len(content))
        
        tool_calls = []
        if tools and self._call_count % 2 == 0:
            tool_calls = [{
                "id": f"call_{self._call_count}",
                "type": "function",
                "function": {
                    "name": "python_execute",
                    "arguments": '{"code": "print(\'hello\')"}',
                },
            }]
        
        return content, tool_calls

    def get_usage(self) -> LLMUsage:
        return self._usage

    def reset_usage(self) -> None:
        self._usage = LLMUsage(prompt_tokens=0, completion_tokens=0)
        self._call_count = 0