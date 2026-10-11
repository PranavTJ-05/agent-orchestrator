from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DebateType(str, Enum):
    CRITIC_LOOP = "critic_loop"
    AGENT_VS_AGENT = "agent_vs_agent"
    RESEARCH_LOOP = "research_loop"


class DebateRound:
    def __init__(
        self,
        round_number: int,
        agent_name: str,
        argument: str,
        timestamp: datetime | None = None,
    ):
        self.round_number = round_number
        self.agent_name = agent_name
        self.argument = argument
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "agent_name": self.agent_name,
            "argument": self.argument,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DebateResult:
    topic: str
    debate_type: DebateType
    rounds: list[DebateRound] = field(default_factory=list)
    winner: str | None = None
    judge_score: float = 0.0
    judge_reasoning: str = ""
    concluded_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "debate_type": self.debate_type.value,
            "rounds": [r.to_dict() for r in self.rounds],
            "winner": self.winner,
            "judge_score": self.judge_score,
            "judge_reasoning": self.judge_reasoning,
            "concluded_at": self.concluded_at.isoformat(),
            "total_rounds": len(self.rounds),
        }


@dataclass
class JudgeDecision:
    winner: str
    score: float
    reasoning: str
    round_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "score": self.score,
            "reasoning": self.reasoning,
            "round_scores": self.round_scores,
        }