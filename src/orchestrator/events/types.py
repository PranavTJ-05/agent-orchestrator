from enum import Enum
from datetime import datetime
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_APPROVAL_REQUIRED = "task_approval_required"
    TASK_APPROVED = "task_approved"
    AGENT_REGISTERED = "agent_registered"
    AGENT_UNREGISTERED = "agent_unregistered"
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
    WAVE_STARTED = "wave_started"
    WAVE_COMPLETED = "wave_completed"


@dataclass
class Event:
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "data": self.data,
        }


@dataclass
class TaskStartedEvent(Event):
    def __init__(self, task_id: str, task_description: str, agent: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TASK_STARTED,
            session_id=session_id,
            data={
                "task_id": task_id,
                "task_description": task_description,
                "agent": agent,
            },
        )


@dataclass
class TaskCompletedEvent(Event):
    def __init__(self, task_id: str, task_description: str, agent: str, result: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TASK_COMPLETED,
            session_id=session_id,
            data={
                "task_id": task_id,
                "task_description": task_description,
                "agent": agent,
                "result": result,
            },
        )


@dataclass
class TaskFailedEvent(Event):
    def __init__(self, task_id: str, task_description: str, agent: str, error: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TASK_FAILED,
            session_id=session_id,
            data={
                "task_id": task_id,
                "task_description": task_description,
                "agent": agent,
                "error": error,
            },
        )


@dataclass
class TaskApprovalRequiredEvent(Event):
    def __init__(self, task_id: str, task_description: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TASK_APPROVAL_REQUIRED,
            session_id=session_id,
            data={
                "task_id": task_id,
                "task_description": task_description,
            },
        )


@dataclass
class TaskApprovedEvent(Event):
    def __init__(self, task_id: str, approved_by: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TASK_APPROVED,
            session_id=session_id,
            data={
                "task_id": task_id,
                "approved_by": approved_by,
            },
        )


@dataclass
class AgentRegisteredEvent(Event):
    def __init__(self, agent_name: str, agent_description: str):
        super().__init__(
            event_type=EventType.AGENT_REGISTERED,
            data={
                "agent_name": agent_name,
                "agent_description": agent_description,
            },
        )


@dataclass
class AgentUnregisteredEvent(Event):
    def __init__(self, agent_name: str):
        super().__init__(
            event_type=EventType.AGENT_UNREGISTERED,
            data={
                "agent_name": agent_name,
            },
        )


@dataclass
class ToolExecutedEvent(Event):
    def __init__(self, tool_name: str, tool_input: dict[str, Any], tool_output: str, agent: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TOOL_EXECUTED,
            session_id=session_id,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output": tool_output,
                "agent": agent,
            },
        )


@dataclass
class ToolFailedEvent(Event):
    def __init__(self, tool_name: str, tool_input: dict[str, Any], error: str, agent: str, session_id: str | None = None):
        super().__init__(
            event_type=EventType.TOOL_FAILED,
            session_id=session_id,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "error": error,
                "agent": agent,
            },
        )


@dataclass
class SessionStartedEvent(Event):
    def __init__(self, session_id: str, goal: str):
        super().__init__(
            event_type=EventType.SESSION_STARTED,
            session_id=session_id,
            data={
                "goal": goal,
            },
        )


@dataclass
class SessionCompletedEvent(Event):
    def __init__(self, session_id: str, goal: str, result: str):
        super().__init__(
            event_type=EventType.SESSION_COMPLETED,
            session_id=session_id,
            data={
                "goal": goal,
                "result": result,
            },
        )


@dataclass
class SessionFailedEvent(Event):
    def __init__(self, session_id: str, goal: str, error: str):
        super().__init__(
            event_type=EventType.SESSION_FAILED,
            session_id=session_id,
            data={
                "goal": goal,
                "error": error,
            },
        )


@dataclass
class WaveStartedEvent(Event):
    def __init__(self, wave_number: int, task_ids: list[str], session_id: str | None = None):
        super().__init__(
            event_type=EventType.WAVE_STARTED,
            session_id=session_id,
            data={
                "wave_number": wave_number,
                "task_ids": task_ids,
            },
        )


@dataclass
class WaveCompletedEvent(Event):
    def __init__(self, wave_number: int, task_ids: list[str], session_id: str | None = None):
        super().__init__(
            event_type=EventType.WAVE_COMPLETED,
            session_id=session_id,
            data={
                "wave_number": wave_number,
                "task_ids": task_ids,
            },
        )