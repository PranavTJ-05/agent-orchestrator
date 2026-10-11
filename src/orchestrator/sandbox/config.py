from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SandboxConfig:
    provider: str = "mock"
    api_key: str | None = None
    timeout: int = 30
    template: str | None = None

    @classmethod
    def from_env(cls) -> "SandboxConfig":
        return cls(
            provider=os.getenv("SANDBOX_PROVIDER", "mock"),
            api_key=os.getenv("E2B_API_KEY"),
            timeout=int(os.getenv("SANDBOX_TIMEOUT", "30")),
            template=os.getenv("E2B_TEMPLATE"),
        )


def get_sandbox_config() -> SandboxConfig:
    return SandboxConfig.from_env()


__all__ = ["SandboxConfig", "get_sandbox_config"]