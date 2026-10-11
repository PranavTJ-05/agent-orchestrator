from __future__ import annotations

import asyncio
import json
import os
import random
from typing import Any

from openai import AsyncOpenAI

from .base import LLM, LLMConfig, LLMUsage

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Fallback models to try when primary fails with rate/limit errors
FALLBACK_MODELS = [
    "openrouter/free",
    "openrouter/auto", 
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-7b-it:free",
]
DEFAULT_MODEL = "openrouter/auto"
MAX_RETRIES_PER_MODEL = 2
BASE_RETRY_DELAY = 1.0  # Base delay in seconds
MAX_RETRY_DELAY = 10.0  # Maximum delay


class OpenRouterLLM(LLM):
    def __init__(self, config: LLMConfig | None = None) -> None:
        from dotenv import load_dotenv
        load_dotenv()

        self.config = config or LLMConfig(
            provider="openrouter",
            model=DEFAULT_MODEL,
        )
        api_key = (
            self.config.api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )
        self._usage = LLMUsage()
        # Try models in order: primary, then fallbacks
        self.model_priority = [self.config.model] + [m for m in FALLBACK_MODELS if m != self.config.model]

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

        base_kwargs: dict[str, Any] = {
            "messages": msgs,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        extra_headers = {
            "HTTP-Referer": "https://github.com/agent-orchestrator",
            "X-Title": "AI Agent Orchestrator",
        }
        if tools:
            base_kwargs["tools"] = tools
        if tool_choice:
            base_kwargs["tool_choice"] = tool_choice

        last_error: Exception | None = None
        
        # Try each model in priority order
        for model_idx, model in enumerate(self.model_priority):
            for attempt in range(MAX_RETRIES_PER_MODEL):
                try:
                    kwargs = base_kwargs.copy()
                    kwargs["model"] = model
                    
                    response = await self.client.chat.completions.create(
                        **kwargs,
                        extra_headers=extra_headers,
                    )
                    if not response.choices:
                        last_error = ValueError(f"No choices in response for model {model}")
                    else:
                        choice = response.choices[0]
                        content = choice.message.content or ""
                        tool_calls = []
                        if choice.message.tool_calls:
                            for tc in choice.message.tool_calls:
                                args = tc.function.arguments
                                if not isinstance(args, str):
                                    args = json.dumps(args)
                                tool_calls.append({
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": args,
                                    },
                                })
                        return content, tool_calls
                except Exception as e:
                    last_error = e
                    # Check if we should retry based on status code
                    status = getattr(e, "status_code", None)
                    should_retry = status in (429, 500, 502, 503, 504, 402) or status is None
                    
                    if should_retry and attempt < MAX_RETRIES_PER_MODEL - 1:
                        # Exponential backoff with jitter
                        delay = min(BASE_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                        jitter = random.uniform(0, delay * 0.1)  # Up to 10% jitter
                        total_delay = delay + jitter
                        
                        # Respect retry-after header if present (402, 429)
                        if hasattr(e, 'response') and e.response is not None:
                            retry_after = e.response.headers.get('retry-after')
                            if retry_after:
                                try:
                                    total_delay = max(total_delay, float(retry_after))
                                except ValueError:
                                    pass
                        
                        await asyncio.sleep(total_delay)
                        continue
                    # Don't retry on auth errors or if max retries exceeded for this model
                    if status in (401, 403):
                        raise
                    break  # Try next model

        raise last_error or RuntimeError("OpenRouter generation failed after trying all models")