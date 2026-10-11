from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Awaitable

from .types import DistributedTask, QueueStats, TaskStatus

logger = logging.getLogger(__name__)


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._tasks: dict[str, DistributedTask] = {}
        self._pending: asyncio.Queue = asyncio.Queue()
        self._workers: dict[str, dict] = {}

    async def enqueue(self, goal: str, session_id: str | None = None) -> DistributedTask:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        
        task = DistributedTask(
            task_id=task_id,
            goal=goal,
            session_id=session_id,
        )
        
        self._tasks[task_id] = task
        await self._pending.put(task)
        
        logger.info(f"Task enqueued: {task_id}")
        return task

    async def dequeue(self, timeout: float = 1.0) -> DistributedTask | None:
        try:
            task = await asyncio.wait_for(self._pending.get(), timeout=timeout)
            return task
        except asyncio.TimeoutError:
            return None

    async def get_task(self, task_id: str) -> DistributedTask | None:
        return self._tasks.get(task_id)

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        result: str | None = None,
        error: str | None = None,
        worker_id: str | None = None,
    ) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        if status:
            task.status = status
            if status == TaskStatus.RUNNING:
                task.started_at = datetime.utcnow()
                task.worker_id = worker_id
            elif status == TaskStatus.COMPLETED:
                task.completed_at = datetime.utcnow()
                task.result = result
            elif status == TaskStatus.FAILED:
                task.completed_at = datetime.utcnow()
                task.error = error
        
        logger.info(f"Task updated: {task_id} -> {status}")
        return True

    async def get_stats(self) -> QueueStats:
        stats = QueueStats()
        for task in self._tasks.values():
            if task.status == TaskStatus.PENDING:
                stats.pending_tasks += 1
            elif task.status == TaskStatus.RUNNING:
                stats.running_tasks += 1
            elif task.status == TaskStatus.COMPLETED:
                stats.completed_tasks += 1
            elif task.status == TaskStatus.FAILED:
                stats.failed_tasks += 1
        
        stats.total_workers = len(self._workers)
        return stats

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
        tasks = tasks[:limit]
        
        return [t.to_dict() for t in tasks]

    def register_worker(self, worker_id: str, info: dict) -> None:
        self._workers[worker_id] = info

    def unregister_worker(self, worker_id: str) -> None:
        if worker_id in self._workers:
            del self._workers[worker_id]

    def get_workers(self) -> list[dict[str, Any]]:
        return list(self._workers.values())


from datetime import datetime