import asyncio
import time
import pytest
from burstgate.limiter.rate_limiter import RateLimiter
from burstgate.errors import RateLimitExceeded, ConfigurationError


def test_rate_limiter_sync_context():
    limiter = RateLimiter(limit=10, period=1.0)
    for _ in range(5):
        with limiter.acquire(tokens=1):
            pass
    assert limiter.try_acquire(tokens=5) is True
    assert limiter.try_acquire(tokens=1) is False


def test_rate_limiter_async_context():
    async def _run():
        limiter = RateLimiter(limit=100, period=1.0)
        async with limiter.acquire(tokens=10):
            await asyncio.sleep(0.01)
        assert limiter.try_acquire(tokens=50) is True

    asyncio.run(_run())


def test_rate_limiter_raise_on_limit():
    limiter = RateLimiter(limit=2, period=10.0, raise_on_limit=True)
    assert limiter.try_acquire(1) is True
    assert limiter.try_acquire(1) is True
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.try_acquire(1)
    assert exc.value.retry_after > 0


def test_rate_limiter_algorithms():
    tb = RateLimiter(limit=5, algorithm="token_bucket")
    sw = RateLimiter(limit=5, algorithm="sliding_window")
    lb = RateLimiter(limit=5, algorithm="leaky_bucket")

    assert tb.try_acquire(5) is True
    assert sw.try_acquire(5) is True
    assert lb.try_acquire(5) is True


def test_rate_limiter_invalid():
    with pytest.raises(ConfigurationError):
        RateLimiter(limit=-1)
    with pytest.raises(ConfigurationError):
        RateLimiter(limit=5, algorithm="unknown")
