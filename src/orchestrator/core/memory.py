from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Memory(ABC):

    @abstractmethod
    async def save(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    async def load(self, key: str) -> Any | None:
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...

    @abstractmethod
    async def clear(self) -> None:
        ...
