import time
import pytest
from burstgate.algorithms.sliding_window import SlidingWindow
from burstgate.errors import ConfigurationError


def test_sliding_window_basic():
    sw = SlidingWindow(limit=5, window_size=1.0)
    for _ in range(5):
        allowed, retry = sw.consume(1)
        assert allowed is True
        assert retry == 0.0

    # 6th should fail
    allowed, retry = sw.consume(1)
    assert allowed is False
    assert retry > 0.0


def test_sliding_window_slide():
    sw = SlidingWindow(limit=3, window_size=0.1, granularity=0.02)
    assert sw.consume(3)[0] is True
    assert sw.consume(1)[0] is False

    # Sleep past window
    time.sleep(0.12)
    assert sw.consume(3)[0] is True


def test_sliding_window_invalid():
    with pytest.raises(ConfigurationError):
        SlidingWindow(limit=0)

    with pytest.raises(ConfigurationError):
        SlidingWindow(limit=10, window_size=0)


def test_sliding_window_reset():
    sw = SlidingWindow(limit=2, window_size=10.0)
    assert sw.consume(2)[0] is True
    assert sw.consume(1)[0] is False
    sw.reset()
    assert sw.consume(2)[0] is True
