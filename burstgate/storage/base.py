"""
Base Storage Interface for BurstGate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Tuple, TypeVar

T = TypeVar("T")


class StorageBackend(ABC):
    """Abstract base class for state storage in BurstGate."""

    @abstractmethod
    def get(self, key: str) -> Any:
        """Retrieve stored value for the given key, or None if expired/non-existent."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store a value with an optional time-to-live in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key was deleted, False otherwise."""
        pass

    @abstractmethod
    def atomic_update(
        self,
        key: str,
        update_fn: Callable[[Any], Tuple[Any, T]],
        default: Any = None,
        ttl: Optional[float] = None,
    ) -> T:
        """
        Atomically inspect and update a stored state under mutual exclusion.

        Args:
            key: State identifier.
            update_fn: Function accepting current state, returning (new_state, result).
            default: Default state if key does not exist yet.
            ttl: Optional TTL for the key in seconds.

        Returns:
            The second element (result) returned by update_fn.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored state."""
        pass
