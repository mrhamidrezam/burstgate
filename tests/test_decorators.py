import asyncio
import pytest
from burstgate.decorators import rate_limit
from burstgate.errors import RateLimitExceeded
from burstgate.limiter.rate_limiter import RateLimiter


def test_decorator_sync():
    calls = []

    @rate_limit(limit=5, period=1.0)
    def do_work(x):
        calls.append(x)
        return x * 2

    res = do_work(10)
    assert res == 20
    assert len(calls) == 1


def test_decorator_async():
    async def _run():
        calls = []

        @rate_limit(limit=10, period=1.0)
        async def async_work(msg):
            calls.append(msg)
            return f"done: {msg}"

        res = await async_work("hello")
        assert res == "done: hello"
        assert len(calls) == 1

    asyncio.run(_run())


def test_decorator_dynamic_tokens():
    limiter = RateLimiter(limit=100, period=1.0)

    @rate_limit(limiter=limiter, tokens=lambda text: len(text))
    def process_text(text: str):
        return text.upper()

    res = process_text("hello")
    assert res == "HELLO"


def test_decorator_non_blocking_raise():
    limiter = RateLimiter(limit=1, period=10.0)

    @rate_limit(limiter=limiter, blocking=False)
    def once():
        return 1

    assert once() == 1
    with pytest.raises(RateLimitExceeded):
        once()
