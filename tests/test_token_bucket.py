import time
import pytest
from burstgate.algorithms.token_bucket import TokenBucket
from burstgate.errors import ConfigurationError
from burstgate.storage.memory import MemoryStorage


def test_token_bucket_basic():
    tb = TokenBucket(rate=10, capacity=10)
    assert tb.available_tokens() == 10

    # Consume 4 tokens
    allowed, retry_after = tb.consume(4)
    assert allowed is True
    assert retry_after == 0.0

    # Consume 6 tokens
    allowed, retry_after = tb.consume(6)
    assert allowed is True
    assert retry_after == 0.0

    # Bucket is empty, consume 1 more
    allowed, retry_after = tb.consume(1)
    assert allowed is False
    assert retry_after > 0.0


def test_token_bucket_refill():
    tb = TokenBucket(rate=100, capacity=10)
    # Drain bucket
    allowed, _ = tb.consume(10)
    assert allowed is True

    # Immediate next should fail
    allowed, retry = tb.consume(1)
    assert allowed is False

    # Sleep 0.05s (should refill ~5 tokens)
    time.sleep(0.06)
    allowed, _ = tb.consume(5)
    assert allowed is True


def test_token_bucket_invalid_config():
    with pytest.raises(ConfigurationError):
        TokenBucket(rate=0)

    with pytest.raises(ConfigurationError):
        TokenBucket(rate=-5)

    with pytest.raises(ConfigurationError):
        TokenBucket(rate=10, capacity=0)


def test_token_bucket_reset():
    tb = TokenBucket(rate=10, capacity=10)
    tb.consume(10)
    assert tb.consume(1)[0] is False
    tb.reset()
    assert tb.consume(5)[0] is True
