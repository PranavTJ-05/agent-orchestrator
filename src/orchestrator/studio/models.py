from __future__ import annotations

import re
import shlex
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
REDACTED = "••••••••"


class ApprovalMode(str, Enum):
    AUTO = "auto"    # read-only tools run; anything else asks
    ASK = "ask"      # every call asks
    ALLOW = "allow"  # nothing asks
    BLOCK = "block"  # tools are hidden and never run


class ServerSpec(BaseModel):
    id: str
    name: str
    transport: Literal["stdio", "http", "sse"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: bool = False
    enabled: bool = True
    approval: ApprovalMode = ApprovalMode.AUTO

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG.match(v):
            raise ValueError("id must be 1-32 chars of lowercase letters, digits, '-' or '_'")
        return v

    @model_validator(mode="after")
    def _transport_fields(self) -> "ServerSpec":
        if self.transport == "stdio":
            if self.command and not self.args and " " in self.command.strip():
                parts = shlex.split(self.command)  # "npx -y pkg" typed into one field
                self.command, self.args = parts[0], parts[1:]
            if not (self.command and self.command.strip()):
                raise ValueError("stdio servers need a command")
        else:
            if not self.url or not re.match(r"^https?://", self.url):
                raise ValueError("http/sse servers need an http(s) URL")
        return self

    def redacted(self) -> "ServerSpec":
        """Copy that is safe to send to the browser: secret values are masked."""
        return self.model_copy(update={
            "env": {k: REDACTED for k in self.env},
            "headers": {k: REDACTED for k in self.headers},
        })

    def merge_secrets(self, previous: "ServerSpec | None") -> "ServerSpec":
        """When the UI sends back masked values, keep the stored secret instead."""
        if previous is None:
            return self
        env = {k: (previous.env.get(k, v) if v == REDACTED else v) for k, v in self.env.items()}
        headers = {k: (previous.headers.get(k, v) if v == REDACTED else v) for k, v in self.headers.items()}
        return self.model_copy(update={"env": env, "headers": headers})


class ToolInfo(BaseModel):
    server_id: str
    name: str
    qualified: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    read_only: bool | None = None
    destructive: bool | None = None
    approval: ApprovalMode = ApprovalMode.AUTO

    def needs_approval(self) -> bool:
        if self.approval == ApprovalMode.ALLOW:
            return False
        if self.approval == ApprovalMode.ASK:
            return True
        return self.read_only is not True  # AUTO: unknown or writing tools ask


class ToolResult(BaseModel):
    ok: bool
    text: str
    duration_ms: float = 0.0
    truncated: bool = False
    timed_out: bool = False


class ServerState(BaseModel):
    spec: ServerSpec
    status: Literal["disabled", "connecting", "connected", "error", "needs_auth"] = "disabled"
    error: str | None = None
    tool_count: int = 0
    server_name: str | None = None
    server_version: str | None = None
    connected_at: float | None = None
    auth_url: str | None = None
