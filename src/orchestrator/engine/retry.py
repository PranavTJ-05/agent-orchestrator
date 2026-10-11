from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True


async def with_retry(
    fn: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    policy = policy or RetryPolicy()
    last_exception: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            last_exception = e
            if attempt < policy.max_retries:
                delay = min(policy.base_delay * (2**attempt), policy.max_delay)
                if policy.jitter:
                    delay *= 0.5 + random.random() * 0.5
                await asyncio.sleep(delay)

    raise last_exception  # type: ignore[misc]
