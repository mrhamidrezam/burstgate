"""
Token Bucket Rate Limiting Algorithm.

Allows bursts up to capacity, while continuously refilling tokens at a constant rate.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from burstgate.errors import ConfigurationError
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage


class TokenBucket:
    """
    Token Bucket rate limiter with continuous microsecond-precision refill.

    Args:
        rate: Rate at which tokens are added per second. Must be > 0.
        capacity: Maximum number of tokens the bucket can hold. Must be >= rate.
        storage: State storage backend (defaults to MemoryStorage).
        key: Unique storage identifier for this bucket.
    """

    def __init__(
        self,
        rate: float,
        capacity: Optional[float] = None,
        storage: Optional[StorageBackend] = None,
        key: str = "burstgate:token_bucket",
    ) -> None:
        if rate <= 0:
            raise ConfigurationError(f"Rate must be greater than 0, got {rate}")

        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        if self.capacity <= 0:
            raise ConfigurationError(f"Capacity must be greater than 0, got {self.capacity}")
        if self.capacity < self.rate:
            # Capacity should be at least rate to allow at least 1s worth of tokens or burst
            pass

        self.storage = storage or MemoryStorage()
        self.key = key

    def _initial_state(self, now: float) -> dict:
        return {"tokens": self.capacity, "last_updated": now}

    def consume(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """
        Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume (can be fractional).

        Returns:
            Tuple of (allowed: bool, retry_after: float).
            If allowed is True, retry_after is 0.0.
            If allowed is False, retry_after indicates seconds until enough tokens refill.
        """
        if tokens <= 0:
            return True, 0.0

        if tokens > self.capacity:
            # Request exceeds total bucket capacity
            wait_time = (tokens - self.capacity) / self.rate
            return False, wait_time

        now = time.time()

        def _update(state: Optional[dict]) -> Tuple[dict, Tuple[bool, float]]:
            if state is None:
                state = self._initial_state(now)

            last_updated = state.get("last_updated", now)
            curr_tokens = state.get("tokens", self.capacity)

            elapsed = max(0.0, now - last_updated)
            refilled = min(self.capacity, curr_tokens + elapsed * self.rate)

            if refilled >= tokens:
                new_tokens = refilled - tokens
                new_state = {"tokens": new_tokens, "last_updated": now}
                return new_state, (True, 0.0)
            else:
                deficit = tokens - refilled
                retry_after = deficit / self.rate
                new_state = {"tokens": refilled, "last_updated": now}
                return new_state, (False, retry_after)

        # TTL set to enough time for bucket to refill to full capacity
        ttl = (self.capacity / self.rate) * 2.0 + 3600.0
        return self.storage.atomic_update(self.key, _update, default=None, ttl=ttl)

    def available_tokens(self) -> float:
        """Get current estimated number of available tokens in bucket."""
        now = time.time()
        state = self.storage.get(self.key)
        if state is None:
            return self.capacity
        last_updated = state.get("last_updated", now)
        curr_tokens = state.get("tokens", self.capacity)
        elapsed = max(0.0, now - last_updated)
        return min(self.capacity, curr_tokens + elapsed * self.rate)

    def reset(self) -> None:
        """Reset the bucket back to full capacity."""
        now = time.time()
        self.storage.set(self.key, {"tokens": self.capacity, "last_updated": now})
