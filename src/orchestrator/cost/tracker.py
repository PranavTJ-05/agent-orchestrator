from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger(__name__)


MODEL_PRICING: dict[str, dict[str, float]] = {
    "huggingface": {
        "Qwen/Qwen2.5-7B-Instruct": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
        "meta-llama/Llama-3-8B-Instruct": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
        "mistralai/Mistral-7B-Instruct-v0.2": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
        "default": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
    },
    "openai": {
        "gpt-4": {"input": 0.03, "output": 0.06, "unit": "per_1k_tokens"},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03, "unit": "per_1k_tokens"},
        "gpt-3.5-turbo": {"input": 0.001, "output": 0.002, "unit": "per_1k_tokens"},
        "default": {"input": 0.001, "output": 0.002, "unit": "per_1k_tokens"},
    },
    "openrouter": {
        "openrouter/auto": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
        "default": {"input": 0.0, "output": 0.0, "unit": "per_1k_tokens"},
    },
    "anthropic": {
        "claude-3-opus": {"input": 0.015, "output": 0.075, "unit": "per_1k_tokens"},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015, "unit": "per_1k_tokens"},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125, "unit": "per_1k_tokens"},
        "default": {"input": 0.003, "output": 0.015, "unit": "per_1k_tokens"},
    },
}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens


@dataclass
class CostRecord:
    session_id: str
    agent_name: str
    model: str
    provider: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model": self.model,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat(),
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "total_tokens": self.usage.total_tokens,
            "cost": self.cost,
            "metadata": self.metadata,
        }


class CostTracker:
    def __init__(self) -> None:
        self._records: list[CostRecord] = []
        self._session_costs: dict[str, float] = {}
        self._agent_costs: dict[str, float] = {}
        self._model_costs: dict[str, float] = {}

    def record(
        self,
        session_id: str,
        agent_name: str,
        model: str,
        provider: str,
        usage: TokenUsage,
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        pricing = self._get_pricing(provider, model)
        cost = self._calculate_cost(usage, pricing)
        
        record = CostRecord(
            session_id=session_id,
            agent_name=agent_name,
            model=model,
            provider=provider,
            usage=usage,
            cost=cost,
            metadata=metadata or {},
        )
        
        self._records.append(record)
        
        if session_id not in self._session_costs:
            self._session_costs[session_id] = 0.0
        self._session_costs[session_id] += cost
        
        if agent_name not in self._agent_costs:
            self._agent_costs[agent_name] = 0.0
        self._agent_costs[agent_name] += cost
        
        model_key = f"{provider}/{model}"
        if model_key not in self._model_costs:
            self._model_costs[model_key] = 0.0
        self._model_costs[model_key] += cost
        
        logger.info(f"Cost recorded: {agent_name} | {model_key} | ${cost:.6f}")
        
        return record

    def _get_pricing(self, provider: str, model: str) -> dict[str, float]:
        provider_pricing = MODEL_PRICING.get(provider, MODEL_PRICING.get("openai", {}))
        return provider_pricing.get(model, provider_pricing.get("default", {"input": 0.0, "output": 0.0}))

    def _calculate_cost(self, usage: TokenUsage, pricing: dict[str, float]) -> float:
        input_cost = (usage.prompt_tokens / 1000.0) * pricing.get("input", 0.0)
        output_cost = (usage.completion_tokens / 1000.0) * pricing.get("output", 0.0)
        return input_cost + output_cost

    def get_session_cost(self, session_id: str) -> float:
        return self._session_costs.get(session_id, 0.0)

    def get_agent_cost(self, agent_name: str) -> float:
        return self._agent_costs.get(agent_name, 0.0)

    def get_model_cost(self, provider: str, model: str) -> float:
        model_key = f"{provider}/{model}"
        return self._model_costs.get(model_key, 0.0)

    def get_total_cost(self) -> float:
        return sum(record.cost for record in self._records)

    def get_records(
        self,
        session_id: str | None = None,
        agent_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        records = self._records
        
        if session_id:
            records = [r for r in records if r.session_id == session_id]
        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]
        
        records = records[-limit:]
        return [r.to_dict() for r in records]

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_cost": self.get_total_cost(),
            "total_requests": len(self._records),
            "session_costs": self._session_costs,
            "agent_costs": self._agent_costs,
            "model_costs": self._model_costs,
        }

    def clear(self) -> None:
        self._records.clear()
        self._session_costs.clear()
        self._agent_costs.clear()
        self._model_costs.clear()

    @staticmethod
    def get_available_models() -> dict[str, list[str]]:
        return {provider: list(models.keys()) for provider, models in MODEL_PRICING.items()}