from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from ..llm.base import LLM
from .queue import InMemoryTaskQueue
from .types import DistributedTask, QueueStats, TaskStatus, WorkerInfo
from ..engine.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


class DistributedExecutor:
    def __init__(
        self,
        llm: LLM,
        queue: InMemoryTaskQueue | None = None,
    ) -> None:
        self._llm = llm
        self._queue = queue or InMemoryTaskQueue()
        self._workers: dict[str, WorkerInfo] = {}
        self._orchestrator: AgentOrchestrator | None = None

    async def submit(self, goal: str, session_id: str | None = None) -> DistributedTask:
        return await self._queue.enqueue(goal, session_id)

    async def get_task(self, task_id: str) -> DistributedTask | None:
        return await self._queue.get_task(task_id)

    async def get_stats(self) -> QueueStats:
        return await self._queue.get_stats()

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self._queue.list_tasks(status, limit)

    async def process_next_task(self, worker_id: str) -> DistributedTask | None:
        task = await self._queue.dequeue()
        
        if not task:
            return None
        
        await self._queue.update_task(
            task.task_id,
            status=TaskStatus.RUNNING,
            worker_id=worker_id,
        )
        
        worker_info = self._workers.get(worker_id)
        if worker_info:
            worker_info.current_task_id = task.task_id
        
        return task

    async def complete_task(
        self,
        task_id: str,
        result: str,
    ) -> bool:
        task = await self._queue.get_task(task_id)
        if not task:
            return False
        
        success = await self._queue.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result=result,
        )
        
        if task.worker_id and task.worker_id in self._workers:
            self._workers[task.worker_id].tasks_completed += 1
            self._workers[task.worker_id].current_task_id = None
        
        return success

    async def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> bool:
        task = await self._queue.get_task(task_id)
        if not task:
            return False
        
        success = await self._queue.update_task(
            task_id,
            status=TaskStatus.FAILED,
            error=error,
        )
        
        if task.worker_id and task.worker_id in self._workers:
            self._workers[task.worker_id].tasks_failed += 1
            self._workers[task.worker_id].current_task_id = None
        
        return success

    def register_worker(self, worker_id: str | None = None) -> str:
        worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        
        self._workers[worker_id] = WorkerInfo(
            worker_id=worker_id,
            status="idle",
        )
        
        logger.info(f"Worker registered: {worker_id}")
        return worker_id

    def unregister_worker(self, worker_id: str) -> bool:
        if worker_id in self._workers:
            del self._workers[worker_id]
            logger.info(f"Worker unregistered: {worker_id}")
            return True
        return False

    def get_workers(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._workers.values()]

    async def execute_task(
        self,
        task: DistributedTask,
        orchestrator: AgentOrchestrator,
    ) -> str:
        result = await orchestrator.execute(task.goal, session_id=task.session_id)
        await self.complete_task(task.task_id, result)
        return result


class Worker:
    def __init__(
        self,
        executor: DistributedExecutor,
        worker_id: str | None = None,
    ) -> None:
        self._executor = executor
        self._worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._worker_id = self._executor.register_worker(self._worker_id)
        logger.info(f"Worker {self._worker_id} started")

        while self._running:
            task = await self._executor.process_next_task(self._worker_id)
            
            if task:
                logger.info(f"Processing task: {task.task_id}")
                try:
                    if not self._executor._orchestrator:
                        from ..engine.orchestrator import AgentOrchestrator
                        self._executor._orchestrator = AgentOrchestrator(llm=self._executor._llm)
                    
                    result = await self._executor._orchestrator.execute(
                        task.goal,
                        session_id=task.session_id,
                    )
                    await self._executor.complete_task(task.task_id, result)
                except Exception as e:
                    await self._executor.fail_task(task.task_id, str(e))
            else:
                await asyncio.sleep(1)

    def stop(self) -> None:
        self._running = False
        self._executor.unregister_worker(self._worker_id)
        logger.info(f"Worker {self._worker_id} stopped")