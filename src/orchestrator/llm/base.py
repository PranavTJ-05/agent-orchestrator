from __future__ import annotations

from abc import ABC, abstractmethod
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMConfig:
    provider: str = field(default_factory=lambda: os.getenv("DEFAULT_LLM_PROVIDER", "huggingface"))
    model: str = field(default_factory=lambda: os.getenv("DEFAULT_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
    temperature: float = 0.3
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "1500")))
    api_key: str | None = None


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    max_prompt_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLM(ABC):

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        ...
    
    @abstractmethod
    def get_usage(self) -> LLMUsage:
        ...
    
    @abstractmethod
    def reset_usage(self) -> None:
        ...
