import asyncio
import pytest
from burstgate.algorithms.adaptive import AdaptiveLimiter
from burstgate.errors import ConfigurationError


def test_adaptive_acquire_release():
    al = AdaptiveLimiter(min_limit=2, max_limit=10, initial_limit=3)
    assert al.current_limit == 3
    assert al.active_count == 0

    assert al.try_acquire() is True
    assert al.try_acquire() is True
    assert al.try_acquire() is True
    # At limit now
    assert al.try_acquire() is False

    al.release()
    assert al.active_count == 2
    assert al.try_acquire() is True


def test_adaptive_latency_and_backoff():
    al = AdaptiveLimiter(min_limit=2, max_limit=20, initial_limit=5, backoff_factor=0.5)

    # Establish baseline min_rtt
    al.record_latency(0.010)
    assert al.min_rtt == 0.010

    # Healthy latency increases limit
    initial = al.limit
    al.record_latency(0.011)
    assert al.limit > initial

    # Error triggers multiplicative backoff
    curr = al.limit
    al.record_error()
    assert al.limit < curr


def test_adaptive_probe_context():
    al = AdaptiveLimiter(min_limit=1, max_limit=5, initial_limit=2)

    with al.probe():
        assert al.active_count == 1
    assert al.active_count == 0
    assert al.min_rtt is not None


def test_adaptive_probe_async_context():
    async def _run():
        al = AdaptiveLimiter(min_limit=1, max_limit=5, initial_limit=2)
        async with al.probe_async():
            assert al.active_count == 1
        assert al.active_count == 0
        assert al.min_rtt is not None

    asyncio.run(_run())
