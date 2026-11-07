"""
Unified Rate Limiter for BurstGate.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, Tuple, Union

from burstgate.algorithms.leaky_bucket import LeakyBucket
from burstgate.algorithms.sliding_window import SlidingWindow
from burstgate.algorithms.token_bucket import TokenBucket
from burstgate.errors import AcquireTimeout, ConfigurationError, RateLimitExceeded
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage


class AcquisitionContext:
    """Context manager supporting both synchronous 'with' and asynchronous 'async with'."""

    def __init__(self, limiter: RateLimiter, tokens: float, timeout: Optional[float]) -> None:
        self.limiter = limiter
        self.tokens = tokens
        self.timeout = timeout

    def __enter__(self) -> AcquisitionContext:
        self.limiter.acquire_sync(tokens=self.tokens, timeout=self.timeout)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def __aenter__(self) -> AcquisitionContext:
        await self.limiter.acquire_async(tokens=self.tokens, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class RateLimiter:
    """
    High-performance Rate Limiter supporting synchronous and asynchronous workflows.

    Args:
        limit: Number of operations allowed per period. Must be > 0.
        period: Time period in seconds (e.g. 1.0 for per-second, 60.0 for per-minute).
        burst: Burst capacity allowed (defaults to limit).
        algorithm: Algorithm name ('token_bucket', 'sliding_window', 'leaky_bucket') or instance.
        storage: State storage backend (defaults to MemoryStorage).
        key: Unique identifier for this rate limiter.
        raise_on_limit: If True, non-blocking failures raise RateLimitExceeded.
    """

    def __init__(
        self,
        limit: float,
        period: float = 1.0,
        burst: Optional[float] = None,
        algorithm: Union[str, TokenBucket, SlidingWindow, LeakyBucket] = "token_bucket",
        storage: Optional[StorageBackend] = None,
        key: str = "burstgate:limiter",
        raise_on_limit: bool = False,
    ) -> None:
        if limit <= 0:
            raise ConfigurationError(f"Limit must be > 0, got {limit}")
        if period <= 0:
            raise ConfigurationError(f"Period must be > 0, got {period}")

        self.limit = float(limit)
        self.period = float(period)
        self.burst = float(burst if burst is not None else limit)
        self.storage = storage or MemoryStorage()
        self.key = key
        self.raise_on_limit = raise_on_limit

        # Rate in units per second
        rate_per_sec = self.limit / self.period

        if isinstance(algorithm, str):
            algo_lower = algorithm.lower().replace("-", "_")
            if algo_lower == "token_bucket":
                self.algorithm = TokenBucket(
                    rate=rate_per_sec,
                    capacity=self.burst,
                    storage=self.storage,
                    key=f"{key}:tb",
                )
            elif algo_lower == "sliding_window":
                self.algorithm = SlidingWindow(
                    limit=self.limit,
                    window_size=self.period,
                    storage=self.storage,
                    key=f"{key}:sw",
                )
            elif algo_lower == "leaky_bucket":
                self.algorithm = LeakyBucket(
                    rate=rate_per_sec,
                    capacity=self.burst,
                    storage=self.storage,
                    key=f"{key}:lb",
                )
            else:
                raise ConfigurationError(
                    f"Unknown algorithm: {algorithm}. Choose 'token_bucket', 'sliding_window', or 'leaky_bucket'."
                )
        else:
            self.algorithm = algorithm

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        Attempt to acquire tokens immediately without blocking.

        Returns:
            True if acquired, False otherwise.

        Raises:
            RateLimitExceeded: If acquisition fails and raise_on_limit is True.
        """
        allowed, retry_after = self.algorithm.consume(tokens)
        if not allowed and self.raise_on_limit:
            raise RateLimitExceeded(
                message=f"Rate limit exceeded on '{self.key}'.",
                retry_after=retry_after,
                limit=self.limit,
                period=self.period,
                resource="requests",
            )
        return allowed

    def retry_after(self, tokens: float = 1.0) -> float:
        """Calculate wait time in seconds if tokens cannot be acquired immediately."""
        allowed, retry_after = self.algorithm.consume(0.0)
        # Check deficit for requested tokens
        if hasattr(self.algorithm, "available_tokens"):
            avail = self.algorithm.available_tokens()
            if avail >= tokens:
                return 0.0
            rate = getattr(self.algorithm, "rate", 1.0)
            return (tokens - avail) / rate
        return retry_after

    def acquire_sync(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Synchronously acquire tokens, sleeping until available or timeout is reached.

        Returns:
            True if acquired, False if timed out.
        """
        start = time.monotonic()
        while True:
            allowed, retry_after = self.algorithm.consume(tokens)
            if allowed:
                return True

            if timeout is not None:
                elapsed = time.monotonic() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    if self.raise_on_limit:
                        raise AcquireTimeout(timeout=timeout)
                    return False
                sleep_duration = min(retry_after, remaining)
            else:
                sleep_duration = max(0.001, retry_after)

            time.sleep(sleep_duration)

    async def acquire_async(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Asynchronously acquire tokens, pausing via asyncio.sleep until available or timeout.

        Returns:
            True if acquired, False if timed out.
        """
        start = time.monotonic()
        while True:
            allowed, retry_after = self.algorithm.consume(tokens)
            if allowed:
                return True

            if timeout is not None:
                elapsed = time.monotonic() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    if self.raise_on_limit:
                        raise AcquireTimeout(timeout=timeout)
                    return False
                sleep_duration = min(retry_after, remaining)
            else:
                sleep_duration = max(0.001, retry_after)

            await asyncio.sleep(sleep_duration)

    def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> AcquisitionContext:
        """
        Context manager for rate-limited execution block.

        Usage:
            with limiter.acquire(tokens=1):
                ...

            async with limiter.acquire(tokens=1):
                ...
        """
        return AcquisitionContext(self, tokens=tokens, timeout=timeout)
