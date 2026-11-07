"""
BurstGate: Resilient, zero-dependency rate limiting, dual-resource token budgeting (RPM/TPM),
and adaptive concurrency control for Python 3.10+.
"""

from burstgate.algorithms.adaptive import AdaptiveLimiter
from burstgate.algorithms.leaky_bucket import LeakyBucket
from burstgate.algorithms.sliding_window import SlidingWindow
from burstgate.algorithms.token_bucket import TokenBucket
from burstgate.decorators import rate_limit
from burstgate.errors import (
    AcquireTimeout,
    BudgetExceeded,
    BurstGateError,
    ConfigurationError,
    RateLimitExceeded,
)
from burstgate.limiter.dual_limiter import (
    DualAcquisitionContext,
    DualLimiter,
    DualTicket,
    estimate_tokens,
)
from burstgate.limiter.rate_limiter import AcquisitionContext, RateLimiter
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage
from burstgate.storage.sqlite import SQLiteStorage

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Algorithms
    "TokenBucket",
    "SlidingWindow",
    "LeakyBucket",
    "AdaptiveLimiter",
    # Limiters
    "RateLimiter",
    "AcquisitionContext",
    "DualLimiter",
    "DualTicket",
    "DualAcquisitionContext",
    "estimate_tokens",
    # Storage
    "StorageBackend",
    "MemoryStorage",
    "SQLiteStorage",
    # Decorators
    "rate_limit",
    # Errors
    "BurstGateError",
    "ConfigurationError",
    "RateLimitExceeded",
    "BudgetExceeded",
    "AcquireTimeout",
]
