from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    goal: str = Field(..., description="The user's goal or request")
    session_id: str | None = None


class ExecuteResponse(BaseModel):
    session_id: str
    result: str


class StatusResponse(BaseModel):
    session_id: str
    result: str | None = None
    complete: bool = False
    plan: Any = None


class AgentRegisterRequest(BaseModel):
    name: str
    description: str
    system_prompt: str | None = None
