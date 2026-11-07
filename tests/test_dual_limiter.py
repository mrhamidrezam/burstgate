import asyncio
import pytest
from burstgate.limiter.dual_limiter import DualLimiter, estimate_tokens
from burstgate.errors import BudgetExceeded


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("Hello world!") >= 2
    long_code = "def foo():\n    return 42\n" * 10
    assert estimate_tokens(long_code) > 20


def test_dual_limiter_sync():
    # 60 RPM, 600 TPM -> 1 req/s, 10 tokens/s, burst = 10 reqs, 300 tokens
    dl = DualLimiter(rpm=60, tpm=600, burst_rpm=5, burst_tpm=100)

    # Initial acquire should succeed
    with dl.acquire(requests=1, tokens=50) as ticket:
        assert ticket.tokens == 50

    # Consuming beyond token limit
    allowed = dl.try_acquire(requests=1, tokens=80)
    assert allowed is False


def test_dual_limiter_ticket_adjust():
    dl = DualLimiter(rpm=60, tpm=1000, burst_rpm=10, burst_tpm=500)

    # Acquire with estimate 100 tokens
    with dl.acquire(tokens=100) as ticket:
        # LLM completed with only 60 tokens, refund 40 tokens
        ticket.adjust(actual_tokens=60)
        assert ticket.tokens == 60

    # Acquire another ticket with estimate 50 and adjust up to 90
    with dl.acquire(tokens=50) as ticket:
        ticket.adjust(actual_tokens=90)
        assert ticket.tokens == 90


def test_dual_limiter_async():
    async def _run():
        dl = DualLimiter(rpm=600, tpm=60000, burst_rpm=50, burst_tpm=5000)
        async with dl.acquire(tokens=200) as ticket:
            await asyncio.sleep(0.01)
            ticket.adjust(actual_tokens=180)
        assert ticket.tokens == 180

    asyncio.run(_run())


def test_dual_limiter_raise_on_limit():
    dl = DualLimiter(rpm=60, tpm=100, burst_rpm=1, burst_tpm=50, raise_on_limit=True)
    assert dl.try_acquire(requests=1, tokens=40) is True
    with pytest.raises(BudgetExceeded):
        dl.try_acquire(requests=1, tokens=40)
