"""
BurstGate Exceptions Module.

Defines custom exception hierarchy for rate limiting and budget violations.
"""

from __future__ import annotations

from typing import Optional


class BurstGateError(Exception):
    """Base exception for all BurstGate errors."""
    pass


class ConfigurationError(BurstGateError):
    """Raised when an invalid configuration is provided to a limiter or algorithm."""
    pass


class RateLimitExceeded(BurstGateError):
    """
    Raised when an operation exceeds the permitted rate limit and blocking is disabled.

    Attributes:
        retry_after: Number of seconds before the operation can be retried.
        limit: The threshold limit configured.
        period: The time window/period in seconds for the limit.
        resource: Name of the resource or bucket that caused the violation.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        retry_after: float = 0.0,
        limit: Optional[float] = None,
        period: Optional[float] = None,
        resource: str = "requests",
    ) -> None:
        super().__init__(message)
        self.retry_after = max(0.0, float(retry_after))
        self.limit = limit
        self.period = period
        self.resource = resource

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} (Resource: {self.resource}, Retry-After: {self.retry_after:.3f}s)"


class BudgetExceeded(RateLimitExceeded):
    """
    Raised when an LLM token or dual-budget constraint is exceeded.

    Attributes:
        requested_tokens: The amount of tokens requested.
        available_tokens: The current amount of tokens available.
    """

    def __init__(
        self,
        message: str = "Budget quota exceeded.",
        retry_after: float = 0.0,
        limit: Optional[float] = None,
        period: Optional[float] = None,
        resource: str = "tokens",
        requested_tokens: Optional[float] = None,
        available_tokens: Optional[float] = None,
    ) -> None:
        super().__init__(
            message=message,
            retry_after=retry_after,
            limit=limit,
            period=period,
            resource=resource,
        )
        self.requested_tokens = requested_tokens
        self.available_tokens = available_tokens


class AcquireTimeout(BurstGateError, TimeoutError):
    """Raised when waiting to acquire a permit exceeds the configured timeout."""

    def __init__(
        self,
        message: str = "Timed out waiting to acquire rate limit permit.",
        timeout: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.timeout = timeout
