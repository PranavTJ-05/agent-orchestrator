from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .task import TaskNode, TaskStatus


class ExecutionState(BaseModel):
    session_id: str
    goal: str
    tasks: list[TaskNode] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    current_task_index: int = 0

    @property
    def current_task(self) -> TaskNode | None:
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    @property
    def completed_tasks(self) -> list[TaskNode]:
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    @property
    def failed_tasks(self) -> list[TaskNode]:
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    @property
    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED) for t in self.tasks)

    def add_task(self, task: TaskNode) -> None:
        self.tasks.append(task)

    def update_task(self, task_id: str, **updates: Any) -> None:
        for t in self.tasks:
            if t.id == task_id:
                for k, v in updates.items():
                    setattr(t, k, v)
                break

    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        return super().model_dump(*args, **kwargs)
