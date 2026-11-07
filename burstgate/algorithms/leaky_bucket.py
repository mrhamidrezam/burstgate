"""
Leaky Bucket Rate Limiting Algorithm.

Smooths out bursty traffic into a stable, constant outflow rate.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from burstgate.errors import ConfigurationError
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage


class LeakyBucket:
    """
    Leaky Bucket traffic shaper.

    Incoming requests add water to the bucket. Water leaks out at a constant
    rate. If incoming requests overflow the bucket capacity, they are rejected
    or delayed.

    Args:
        rate: Leak rate in units per second. Must be > 0.
        capacity: Maximum capacity of the bucket. Must be >= 1.0.
        storage: State storage backend (defaults to MemoryStorage).
        key: Unique storage identifier for this bucket.
    """

    def __init__(
        self,
        rate: float,
        capacity: float = 10.0,
        storage: Optional[StorageBackend] = None,
        key: str = "burstgate:leaky_bucket",
    ) -> None:
        if rate <= 0:
            raise ConfigurationError(f"Rate must be > 0, got {rate}")
        if capacity <= 0:
            raise ConfigurationError(f"Capacity must be > 0, got {capacity}")

        self.rate = float(rate)
        self.capacity = float(capacity)
        self.storage = storage or MemoryStorage()
        self.key = key

    def consume(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """
        Attempt to add water to the leaky bucket.

        Args:
            tokens: Number of units to add to the bucket.

        Returns:
            Tuple of (allowed: bool, retry_after: float).
        """
        if tokens <= 0:
            return True, 0.0

        if tokens > self.capacity:
            return False, (tokens - self.capacity) / self.rate

        now = time.time()

        def _update(state: Optional[dict]) -> Tuple[dict, Tuple[bool, float]]:
            if state is None:
                state = {"water": 0.0, "last_leak": now}

            last_leak = state.get("last_leak", now)
            curr_water = state.get("water", 0.0)

            elapsed = max(0.0, now - last_leak)
            leaked_water = max(0.0, curr_water - (elapsed * self.rate))

            if leaked_water + tokens <= self.capacity:
                new_water = leaked_water + tokens
                new_state = {"water": new_water, "last_leak": now}
                return new_state, (True, 0.0)
            else:
                overflow = (leaked_water + tokens) - self.capacity
                retry_after = overflow / self.rate
                new_state = {"water": leaked_water, "last_leak": now}
                return new_state, (False, retry_after)

        ttl = (self.capacity / self.rate) * 2.0 + 3600.0
        return self.storage.atomic_update(self.key, _update, default=None, ttl=ttl)

    def current_water(self) -> float:
        """Get the current estimated water level in the bucket."""
        now = time.time()
        state = self.storage.get(self.key)
        if not state:
            return 0.0
        last_leak = state.get("last_leak", now)
        curr_water = state.get("water", 0.0)
        elapsed = max(0.0, now - last_leak)
        return max(0.0, curr_water - (elapsed * self.rate))

    def reset(self) -> None:
        """Empty the leaky bucket."""
        now = time.time()
        self.storage.set(self.key, {"water": 0.0, "last_leak": now})
