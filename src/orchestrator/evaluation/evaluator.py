from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskEvaluation:
    task_id: str
    agent_name: str
    session_id: str
    success: bool
    completed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    error: str | None = None
    tools_used: int = 0
    tools_succeeded: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "success": self.success,
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "tools_used": self.tools_used,
            "tools_succeeded": self.tools_succeeded,
            "tool_success_rate": self.tools_succeeded / self.tools_used if self.tools_used > 0 else 0.0,
        }


@dataclass
class AgentMetrics:
    agent_name: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_duration_ms: float = 0.0
    total_tools_used: int = 0
    total_tools_succeeded: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    @property
    def tool_success_rate(self) -> float:
        if self.total_tools_used == 0:
            return 0.0
        return self.total_tools_succeeded / self.total_tools_used

    @property
    def avg_duration_ms(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_duration_ms / self.total_tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": round(self.success_rate, 3),
            "tool_success_rate": round(self.tool_success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_tools_used": self.total_tools_used,
            "total_tools_succeeded": self.total_tools_succeeded,
        }


@dataclass
class SessionEvaluation:
    session_id: str
    goal: str
    success: bool
    completed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "success": self.success,
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "completion_rate": self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0.0,
        }


class AgentEvaluator:
    def __init__(self) -> None:
        self._task_evaluations: list[TaskEvaluation] = []
        self._agent_metrics: dict[str, AgentMetrics] = {}
        self._session_evaluations: list[SessionEvaluation] = []

    def record_task(
        self,
        task_id: str,
        agent_name: str,
        session_id: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        tools_used: int = 0,
        tools_succeeded: int = 0,
    ) -> TaskEvaluation:
        evaluation = TaskEvaluation(
            task_id=task_id,
            agent_name=agent_name,
            session_id=session_id,
            success=success,
            duration_ms=duration_ms,
            error=error,
            tools_used=tools_used,
            tools_succeeded=tools_succeeded,
        )
        
        self._task_evaluations.append(evaluation)
        
        if agent_name not in self._agent_metrics:
            self._agent_metrics[agent_name] = AgentMetrics(agent_name=agent_name)
        
        metrics = self._agent_metrics[agent_name]
        metrics.total_tasks += 1
        if success:
            metrics.successful_tasks += 1
        else:
            metrics.failed_tasks += 1
        metrics.total_duration_ms += duration_ms
        metrics.total_tools_used += tools_used
        metrics.total_tools_succeeded += tools_succeeded
        
        logger.info(f"Task evaluated: {task_id} | {agent_name} | success={success}")
        
        return evaluation

    def record_session(
        self,
        session_id: str,
        goal: str,
        success: bool,
        duration_ms: float,
        total_tasks: int,
        completed_tasks: int,
        failed_tasks: int,
    ) -> SessionEvaluation:
        evaluation = SessionEvaluation(
            session_id=session_id,
            goal=goal,
            success=success,
            duration_ms=duration_ms,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
        )
        
        self._session_evaluations.append(evaluation)
        logger.info(f"Session evaluated: {session_id} | success={success}")
        
        return evaluation

    def get_agent_metrics(self, agent_name: str | None = None) -> dict[str, Any]:
        if agent_name:
            metrics = self._agent_metrics.get(agent_name)
            if metrics:
                return metrics.to_dict()
            return {}
        
        return {
            name: metrics.to_dict()
            for name, metrics in self._agent_metrics.items()
        }

    def get_session_evaluation(self, session_id: str) -> dict[str, Any] | None:
        for eval in self._session_evaluations:
            if eval.session_id == session_id:
                return eval.to_dict()
        return None

    def get_task_evaluations(
        self,
        session_id: str | None = None,
        agent_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        evaluations = self._task_evaluations
        
        if session_id:
            evaluations = [e for e in evaluations if e.session_id == session_id]
        if agent_name:
            evaluations = [e for e in evaluations if e.agent_name == agent_name]
        
        evaluations = evaluations[-limit:]
        return [e.to_dict() for e in evaluations]

    def get_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        sorted_agents = sorted(
            self._agent_metrics.values(),
            key=lambda m: m.success_rate,
            reverse=True,
        )
        return [m.to_dict() for m in sorted_agents[:limit]]

    def get_summary(self) -> dict[str, Any]:
        total_tasks = sum(m.total_tasks for m in self._agent_metrics.values())
        successful_tasks = sum(m.successful_tasks for m in self._agent_metrics.values())
        
        return {
            "total_tasks_evaluated": total_tasks,
            "successful_tasks": successful_tasks,
            "failed_tasks": total_tasks - successful_tasks,
            "overall_success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0.0,
            "total_sessions": len(self._session_evaluations),
            "successful_sessions": sum(1 for s in self._session_evaluations if s.success),
            "agents_evaluated": len(self._agent_metrics),
        }

    def clear(self) -> None:
        self._task_evaluations.clear()
        self._agent_metrics.clear()
        self._session_evaluations.clear()