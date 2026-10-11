from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from enum import Enum


class Capability(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    WRITING = "writing"
    ANALYSIS = "analysis"
    WEB_SEARCH = "web_search"
    FILE_OPS = "file_operations"
    CODE_EXECUTION = "code_execution"
    GITHUB = "github"
    DATABASE = "database"
    FINANCE = "finance"
    CRITIQUE = "critique"
    REVIEW = "review"
    PLANNING = "planning"
    ROUTING = "routing"
    SYNTHESIS = "synthesis"
    DELEGATION = "delegation"


@dataclass
class AgentCapability:
    capability: Capability
    score: float = 1.0
    description: str = ""


@dataclass
class AgentRegistration:
    name: str
    description: str
    capabilities: list[AgentCapability] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_capability(self, capability: Capability) -> bool:
        return any(c.capability == capability for c in self.capabilities)

    def get_capability_score(self, capability: Capability) -> float:
        for c in self.capabilities:
            if c.capability == capability:
                return c.score
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [
                {
                    "capability": c.capability.value,
                    "score": c.score,
                    "description": c.description,
                }
                for c in self.capabilities
            ],
            "metadata": self.metadata,
        }