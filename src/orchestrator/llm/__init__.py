from .anthropic_llm import AnthropicLLM
from .base import LLM, LLMConfig
from .huggingface_llm import HuggingFaceLLM
from .mock_llm import MockLLM
from .openai_compat_llm import GeminiLLM, GroqLLM
from .openai_llm import OpenAILLM
from .openrouter_llm import OpenRouterLLM

__all__ = [
    "AnthropicLLM",
    "GeminiLLM",
    "GroqLLM",
    "HuggingFaceLLM",
    "LLM",
    "LLMConfig",
    "MockLLM",
    "OpenAILLM",
    "OpenRouterLLM",
]


def create_llm(config: LLMConfig | None = None) -> LLM:
    config = config or LLMConfig()
    if config.provider == "openai":
        return OpenAILLM(config)
    elif config.provider == "anthropic":
        return AnthropicLLM(config)
    elif config.provider == "huggingface":
        return HuggingFaceLLM(config)
    elif config.provider == "openrouter":
        return OpenRouterLLM(config)
    elif config.provider == "groq":
        return GroqLLM(config)
    elif config.provider == "gemini":
        return GeminiLLM(config)
    elif config.provider == "mock":
        return MockLLM(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
