from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .task import TaskNode
from ..core.state import ExecutionState


@dataclass
class BaseAgent(ABC):
    name: str
    description: str
    tools: list = field(default_factory=list)

    @abstractmethod
    async def run(self, task: TaskNode, state: ExecutionState | None = None) -> str:
        ...

    def to_registration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tools": [t.name for t in self.tools],
        }
