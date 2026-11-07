import time
import pytest
from burstgate.algorithms.leaky_bucket import LeakyBucket
from burstgate.errors import ConfigurationError


def test_leaky_bucket_basic():
    lb = LeakyBucket(rate=10, capacity=5)
    # Fill up to capacity
    assert lb.consume(5)[0] is True

    # Next should overflow
    allowed, retry = lb.consume(1)
    assert allowed is False
    assert retry > 0.0


def test_leaky_bucket_leak():
    lb = LeakyBucket(rate=50, capacity=5)
    assert lb.consume(5)[0] is True
    assert lb.consume(1)[0] is False

    # Wait 0.05s (leaks ~2.5 tokens)
    time.sleep(0.06)
    assert lb.consume(2)[0] is True


def test_leaky_bucket_invalid():
    with pytest.raises(ConfigurationError):
        LeakyBucket(rate=0)
    with pytest.raises(ConfigurationError):
        LeakyBucket(rate=5, capacity=0)


def test_leaky_bucket_reset():
    lb = LeakyBucket(rate=5, capacity=5)
    lb.consume(5)
    assert lb.consume(1)[0] is False
    lb.reset()
    assert lb.consume(5)[0] is True
