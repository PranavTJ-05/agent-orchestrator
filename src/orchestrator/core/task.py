from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


class EdgeType(StrEnum):
    DEPENDENCY = "dependency"
    CONDITIONAL = "conditional"


class TaskEdge(BaseModel):
    source: str
    target: str
    edge_type: EdgeType = EdgeType.DEPENDENCY
    condition: str | None = None  # e.g., "if result contains 'error' then skip"


class TaskNode(BaseModel):
    id: str
    description: str
    agent: str | None = None
    deps: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    requires_approval: bool = False
    approved_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    goal: str
    tasks: list[TaskNode]

    def dependency_graph(self) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for t in self.tasks:
            graph[t.id] = t.deps
        return graph

    def to_dag(self) -> dict[str, Any]:
        """Convert plan to DAG representation with nodes and edges."""
        nodes = []
        edges = []
        
        for task in self.tasks:
            nodes.append({
                "id": task.id,
                "description": task.description,
                "agent": task.agent,
                "status": task.status.value,
                "requires_approval": task.requires_approval,
            })
            
            for dep in task.deps:
                edges.append({
                    "source": dep,
                    "target": task.id,
                    "edge_type": EdgeType.DEPENDENCY.value,
                })
        
        return {
            "goal": self.goal,
            "nodes": nodes,
            "edges": edges,
        }

    def topological_waves(self) -> list[list[TaskNode]]:
        remaining = {t.id: t for t in self.tasks}
        completed: set[str] = set()
        waves: list[list[TaskNode]] = []

        while remaining:
            wave = [
                t
                for t in remaining.values()
                if all(d in completed and remaining.get(d) is None or d in completed for d in t.deps)
            ]
            wave = [t for t in wave if all(d in completed for d in t.deps)]
            if not wave:
                remaining_ids = list(remaining.keys())
                wave = [remaining[remaining_ids[0]]]
            waves.append(wave)
            for t in wave:
                completed.add(t.id)
                del remaining[t.id]

        return waves


# Alias for backward compatibility
Task = TaskNode
