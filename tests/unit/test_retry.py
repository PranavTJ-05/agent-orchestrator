import pytest
from src.orchestrator.engine.retry import RetryPolicy, with_retry


class TestRetry:
    async def test_success_no_retry(self) -> None:
        async def fn() -> str:
            return "ok"

        result = await with_retry(fn)
        assert result == "ok"

    async def test_retry_on_failure(self) -> None:
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "ok"

        result = await with_retry(fn, policy=RetryPolicy(max_retries=3, base_delay=0.01))
        assert result == "ok"
        assert call_count == 3

    async def test_exhaust_retries(self) -> None:
        async def fn() -> str:
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await with_retry(fn, policy=RetryPolicy(max_retries=2, base_delay=0.01))
