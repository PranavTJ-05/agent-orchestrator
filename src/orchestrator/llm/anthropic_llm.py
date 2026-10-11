from __future__ import annotations

import json
import os
from typing import Any

from anthropic import AsyncAnthropic

from .base import LLM, LLMConfig, LLMUsage


class AnthropicLLM(LLM):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig(provider="anthropic", model="claude-sonnet-4-20250514")
        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(api_key=api_key)
        self._usage = LLMUsage()

    def get_usage(self) -> LLMUsage:
        return self._usage

    def reset_usage(self) -> None:
        self._usage = LLMUsage()

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        msgs = messages or []

        antr_tools = None
        if tools:
            antr_tools = []
            for t in tools:
                fn = t.get("function", t)
                antr_tools.append({
                    "name": fn.get("name", "unknown"),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })

        response = await self.client.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=msgs,
            tools=antr_tools or [],
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )

        content = ""
        tool_calls: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })

        return content, tool_calls
