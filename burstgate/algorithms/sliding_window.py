"""
Sliding Window Rate Limiting Algorithm.

Prevents traffic spikes at window boundaries by tracking consumption over a rolling time window.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from burstgate.errors import ConfigurationError
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage


class SlidingWindow:
    """
    Sliding Window rate limiter with sub-interval aggregation.

    Args:
        limit: Maximum units allowed within the sliding window. Must be > 0.
        window_size: Window size in seconds (e.g., 60.0 for 1 minute). Must be > 0.
        granularity: Sub-interval grouping in seconds to keep state compact.
        storage: State storage backend (defaults to MemoryStorage).
        key: Unique storage identifier for this window.
    """

    def __init__(
        self,
        limit: float,
        window_size: float = 60.0,
        granularity: float = 0.5,
        storage: Optional[StorageBackend] = None,
        key: str = "burstgate:sliding_window",
    ) -> None:
        if limit <= 0:
            raise ConfigurationError(f"Limit must be > 0, got {limit}")
        if window_size <= 0:
            raise ConfigurationError(f"Window size must be > 0, got {window_size}")

        self.limit = float(limit)
        self.window_size = float(window_size)
        self.granularity = max(0.01, float(granularity))
        self.storage = storage or MemoryStorage()
        self.key = key

    def consume(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """
        Attempt to consume tokens within the rolling window.

        Args:
            tokens: Number of units/tokens to consume.

        Returns:
            Tuple of (allowed: bool, retry_after: float).
        """
        if tokens <= 0:
            return True, 0.0

        if tokens > self.limit:
            # Single request exceeds entire window capacity
            return False, self.window_size

        now = time.time()
        window_start = now - self.window_size
        rounded_ts = round(now / self.granularity) * self.granularity

        def _update(state: Optional[dict]) -> Tuple[dict, Tuple[bool, float]]:
            entries: List[List[float]] = state.get("entries", []) if state else []

            # Prune entries outside rolling window
            valid_entries = [e for e in entries if e[0] > window_start]
            current_usage = sum(e[1] for e in valid_entries)

            if current_usage + tokens <= self.limit:
                # Add to current bucket
                if valid_entries and abs(valid_entries[-1][0] - rounded_ts) < (self.granularity / 2.0):
                    valid_entries[-1][1] += tokens
                else:
                    valid_entries.append([rounded_ts, tokens])

                new_state = {"entries": valid_entries}
                return new_state, (True, 0.0)
            else:
                # Calculate time until enough tokens expire
                needed = (current_usage + tokens) - self.limit
                freed = 0.0
                retry_after = self.window_size
                for entry_ts, entry_tokens in valid_entries:
                    freed += entry_tokens
                    if freed >= needed:
                        retry_after = max(0.001, (entry_ts + self.window_size) - now)
                        break

                new_state = {"entries": valid_entries}
                return new_state, (False, retry_after)

        ttl = self.window_size * 2.0
        return self.storage.atomic_update(self.key, _update, default=None, ttl=ttl)

    def current_usage(self) -> float:
        """Calculate total units consumed within the active window."""
        now = time.time()
        window_start = now - self.window_size
        state = self.storage.get(self.key)
        if not state:
            return 0.0
        entries = state.get("entries", [])
        return sum(e[1] for e in entries if e[0] > window_start)

    def reset(self) -> None:
        """Reset the sliding window state."""
        self.storage.set(self.key, {"entries": []})
