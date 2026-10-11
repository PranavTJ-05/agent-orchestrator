from __future__ import annotations

import asyncio
import os
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from .base import LLMConfig, LLMUsage
from .openai_llm import OpenAILLM

MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_WAIT = 30.0


class _OpenAICompatLLM(OpenAILLM):
    """OpenAI-compatible provider: same chat API, different base URL and key."""

    base_url: str
    api_key_env: str
    provider: str
    default_model: str

    def __init__(self, config: LLMConfig | None = None) -> None:
        from dotenv import load_dotenv
        load_dotenv()

        self.config = config or LLMConfig(provider=self.provider, model=self.default_model)
        api_key = self.config.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise ValueError(f"{self.api_key_env} is not set (add it to .env)")
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.base_url, max_retries=0)
        self._usage = LLMUsage()

    async def generate(self, *args: Any, **kwargs: Any) -> tuple[str, list[dict[str, Any]]]:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                return await super().generate(*args, **kwargs)
            except RateLimitError as e:
                # 413 = one request is bigger than the per-minute limit; waiting cannot fix it.
                if getattr(e, "status_code", None) == 413 or attempt == MAX_RATE_LIMIT_RETRIES:
                    raise
                retry_after = e.response.headers.get("retry-after") if e.response else None
                try:
                    wait = float(retry_after) if retry_after else 2.0 ** (attempt + 1)
                except ValueError:
                    wait = 2.0 ** (attempt + 1)
                await asyncio.sleep(min(wait, MAX_RETRY_WAIT))
        raise RuntimeError("unreachable")


class GroqLLM(_OpenAICompatLLM):
    base_url = "https://api.groq.com/openai/v1"
    api_key_env = "GROQ_API_KEY"
    provider = "groq"
    default_model = "openai/gpt-oss-120b"

    def _extra_body(self) -> dict[str, Any] | None:
        # gpt-oss models spend hidden reasoning tokens that count toward the TPM limit
        if "gpt-oss" in self.config.model:
            return {"reasoning_effort": os.getenv("GROQ_REASONING_EFFORT", "low")}
        return None


class GeminiLLM(_OpenAICompatLLM):
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    api_key_env = "GEMINI_API_KEY"
    provider = "gemini"
    default_model = "gemini-2.0-flash"
