from __future__ import annotations

from typing import Any

from ..core.memory import Memory


class ShortTermMemory(Memory):
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def save(self, key: str, value: Any) -> None:
        self._store[key] = value

    async def load(self, key: str) -> Any | None:
        return self._store.get(key)

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for k, v in self._store.items():
            if query_lower in k.lower():
                results.append({"key": k, "value": v})
            if len(results) >= limit:
                break
        return results

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    @property
    def all(self) -> dict[str, Any]:
        return dict(self._store)
