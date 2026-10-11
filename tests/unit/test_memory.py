import pytest
from src.orchestrator.memory.short_term import ShortTermMemory


@pytest.mark.asyncio
class TestShortTermMemory:
    async def test_save_and_load(self) -> None:
        mem = ShortTermMemory()
        await mem.save("key1", "value1")
        result = await mem.load("key1")
        assert result == "value1"

    async def test_load_missing(self) -> None:
        mem = ShortTermMemory()
        result = await mem.load("nonexistent")
        assert result is None

    async def test_delete(self) -> None:
        mem = ShortTermMemory()
        await mem.save("key1", "value1")
        await mem.delete("key1")
        assert await mem.load("key1") is None

    async def test_clear(self) -> None:
        mem = ShortTermMemory()
        await mem.save("a", "1")
        await mem.save("b", "2")
        await mem.clear()
        assert await mem.load("a") is None
        assert await mem.load("b") is None

    async def test_search(self) -> None:
        mem = ShortTermMemory()
        await mem.save("session:abc:plan", "plan_data")
        await mem.save("session:abc:result", "result_data")
        results = await mem.search("session:abc")
        assert len(results) == 2
