"""
Adaptive Concurrency Controller.

Dynamically adjusts concurrency limits based on observed latency (RTT)
and error feedback (e.g., HTTP 429 / 503), inspired by TCP Vegas and Netflix Concurrency Limits.
"""

from __future__ import annotations

import math
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from burstgate.errors import ConfigurationError


class AdaptiveLimiter:
    """
    Self-tuning adaptive concurrency limiter.

    Automatically expands concurrency when downstream latency is healthy,
    and throttles down immediately when latency degrades or errors are observed.

    Args:
        min_limit: Floor limit for concurrency. Defaults to 1.
        max_limit: Ceiling limit for concurrency. Defaults to 100.
        initial_limit: Initial starting concurrency limit. Defaults to 5.
        backoff_factor: Multiplier to scale down limit on error (e.g. 0.7 for 30% reduction).
        tolerance: Latency threshold factor relative to min_rtt before throttling (e.g. 1.3 = 30% latency increase allowed).
    """

    def __init__(
        self,
        min_limit: int = 1,
        max_limit: int = 100,
        initial_limit: int = 5,
        backoff_factor: float = 0.7,
        tolerance: float = 1.3,
    ) -> None:
        if min_limit < 1:
            raise ConfigurationError(f"min_limit must be >= 1, got {min_limit}")
        if max_limit < min_limit:
            raise ConfigurationError(f"max_limit ({max_limit}) must be >= min_limit ({min_limit})")

        self.min_limit = int(min_limit)
        self.max_limit = int(max_limit)
        self.limit = float(initial_limit)
        self.backoff_factor = float(backoff_factor)
        self.tolerance = float(tolerance)

        self._active = 0
        self._min_rtt: Optional[float] = None
        self._ema_rtt: Optional[float] = None
        self._lock = threading.RLock()

    @property
    def current_limit(self) -> int:
        """Current integer concurrency limit."""
        with self._lock:
            return max(self.min_limit, min(self.max_limit, int(math.floor(self.limit))))

    @property
    def active_count(self) -> int:
        """Number of currently active in-flight requests."""
        with self._lock:
            return self._active

    @property
    def min_rtt(self) -> Optional[float]:
        """Observed minimum round-trip time in seconds."""
        with self._lock:
            return self._min_rtt

    @property
    def average_rtt(self) -> Optional[float]:
        """Exponential moving average of round-trip time."""
        with self._lock:
            return self._ema_rtt

    def try_acquire(self) -> bool:
        """Attempt to acquire a concurrency slot without blocking."""
        with self._lock:
            if self._active < self.current_limit:
                self._active += 1
                return True
            return False

    def release(self) -> None:
        """Release an acquired concurrency slot."""
        with self._lock:
            if self._active > 0:
                self._active -= 1

    def record_latency(self, rtt: float) -> None:
        """
        Record observed round-trip time for a successful operation.

        Args:
            rtt: Measured round-trip latency in seconds.
        """
        if rtt <= 0:
            return

        with self._lock:
            if self._min_rtt is None or rtt < self._min_rtt:
                self._min_rtt = rtt

            if self._ema_rtt is None:
                self._ema_rtt = rtt
            else:
                self._ema_rtt = 0.2 * rtt + 0.8 * self._ema_rtt

            threshold = self._min_rtt * self.tolerance
            if rtt <= threshold:
                # Healthy latency: Additive increase
                self.limit = min(float(self.max_limit), self.limit + (1.0 / self.limit))
            else:
                # High queueing latency: Gentle decrease
                self.limit = max(float(self.min_limit), self.limit - 0.5)

    def record_error(self) -> None:
        """
        Record a failure signal (such as HTTP 429, 503, or connection timeout).
        Triggers multiplicative backoff reduction of concurrency limit.
        """
        with self._lock:
            self.limit = max(
                float(self.min_limit),
                self.limit * self.backoff_factor,
            )

    @contextmanager
    def probe(self) -> Generator[None, None, None]:
        """
        Synchronous context manager that measures RTT and reports success/error automatically.
        """
        acquired = self.try_acquire()
        if not acquired:
            raise RuntimeError("Adaptive concurrency limit reached.")

        start = time.perf_counter()
        has_error = False
        try:
            yield
        except Exception:
            has_error = True
            self.record_error()
            raise
        finally:
            self.release()
            if not has_error:
                elapsed = time.perf_counter() - start
                self.record_latency(elapsed)

    @asynccontextmanager
    async def probe_async(self) -> AsyncGenerator[None, None]:
        """
        Asynchronous context manager that measures RTT and reports success/error automatically.
        """
        acquired = self.try_acquire()
        if not acquired:
            raise RuntimeError("Adaptive concurrency limit reached.")

        start = time.perf_counter()
        has_error = False
        try:
            yield
        except Exception:
            has_error = True
            self.record_error()
            raise
        finally:
            self.release()
            if not has_error:
                elapsed = time.perf_counter() - start
                self.record_latency(elapsed)

    def reset(self) -> None:
        """Reset internal metrics and limits."""
        with self._lock:
            self._active = 0
            self._min_rtt = None
            self._ema_rtt = None
            self.limit = float(self.min_limit)
