from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from .base import LLM, LLMConfig, LLMUsage


class OpenAILLM(LLM):
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig(provider="openai")
        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key)
        self._usage = LLMUsage()

    def get_usage(self) -> LLMUsage:
        return self._usage

    def reset_usage(self) -> None:
        self._usage = LLMUsage()

    def _extra_body(self) -> dict[str, Any] | None:
        return None

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self._usage.calls += 1
        self._usage.prompt_tokens += usage.prompt_tokens or 0
        self._usage.completion_tokens += usage.completion_tokens or 0
        self._usage.max_prompt_tokens = max(self._usage.max_prompt_tokens, usage.prompt_tokens or 0)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if messages:
            msgs.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": msgs,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        extra_body = self._extra_body()
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await self.client.chat.completions.create(**kwargs)
        self._record_usage(response)
        choice = response.choices[0]

        content = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        return content, tool_calls
