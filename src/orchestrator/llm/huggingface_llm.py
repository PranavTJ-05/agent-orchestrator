from __future__ import annotations

import json
import os
from typing import Any

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.inference._generated.types.chat_completion import (
    ChatCompletionInputFunctionDefinition,
    ChatCompletionInputTool,
    ChatCompletionOutputComplete,
)

from .base import LLM, LLMConfig, LLMUsage


def _openai_tool_to_hf(tool: dict[str, Any]) -> ChatCompletionInputTool:
    fn = tool.get("function", tool)
    return ChatCompletionInputTool(
        function=ChatCompletionInputFunctionDefinition(
            name=fn.get("name", "unknown"),
            description=fn.get("description", ""),
            parameters=fn.get("parameters", {"type": "object", "properties": {}}),
        ),
        type="function",
    )


class HuggingFaceLLM(LLM):
    def __init__(self, config: LLMConfig | None = None) -> None:
        from dotenv import load_dotenv
        load_dotenv()
        self.config = config or LLMConfig(
            provider="huggingface",
            model="Qwen/Qwen2.5-7B-Instruct",
        )
        api_key = (
            self.config.api_key
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.client = AsyncInferenceClient(
            api_key=api_key,
            base_url="https://router.huggingface.co/v1",
        )
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
        msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if messages:
            msgs.extend(messages)

        hf_tools = None
        if tools:
            hf_tools = [_openai_tool_to_hf(t) for t in tools]

        kwargs: dict[str, Any] = {
            "messages": msgs,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "model": self.config.model,
        }
        if hf_tools:
            kwargs["tools"] = hf_tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = await self.client.chat_completion(**kwargs)
        choice: ChatCompletionOutputComplete = response.choices[0]

        if response.usage:
            self._usage.prompt_tokens = response.usage.prompt_tokens or 0
            self._usage.completion_tokens = response.usage.completion_tokens or 0

        content = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": json.dumps(tc.function.arguments) if not isinstance(tc.function.arguments, str) else tc.function.arguments,
                    },
                })

        return content, tool_calls
