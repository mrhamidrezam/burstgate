"""
Decorators for seamless function and coroutine rate limiting.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, Optional, TypeVar, Union

from burstgate.errors import RateLimitExceeded
from burstgate.limiter.dual_limiter import DualLimiter
from burstgate.limiter.rate_limiter import RateLimiter

F = TypeVar("F", bound=Callable[..., Any])


def rate_limit(
    limiter: Optional[Union[RateLimiter, DualLimiter]] = None,
    limit: Optional[float] = None,
    period: float = 1.0,
    tokens: Union[float, Callable[..., float]] = 1.0,
    blocking: bool = True,
    timeout: Optional[float] = None,
    key: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator to rate limit synchronous or asynchronous functions.

    Can either accept an existing RateLimiter / DualLimiter instance, or create
    one automatically from `limit` and `period`.

    Args:
        limiter: Existing RateLimiter or DualLimiter instance.
        limit: Limit count per period (used if limiter is None).
        period: Time window in seconds (used if limiter is None).
        tokens: Number of tokens or callable taking (*args, **kwargs) -> tokens.
        blocking: If True, waits until capacity is available; if False, raises on limit.
        timeout: Maximum wait time in blocking mode.
        key: Storage key for created limiter.
    """
    if limiter is None:
        if limit is None:
            raise ValueError("Must provide either 'limiter' or 'limit'.")
        limiter_inst: Union[RateLimiter, DualLimiter] = RateLimiter(
            limit=limit,
            period=period,
            key=key or "burstgate:decorator",
            raise_on_limit=not blocking,
        )
    else:
        limiter_inst = limiter

    def decorator(fn: F) -> F:
        is_coroutine = inspect.iscoroutinefunction(fn)

        def _resolve_tokens(args: tuple, kwargs: dict) -> float:
            if callable(tokens):
                return float(tokens(*args, **kwargs))
            return float(tokens)

        if is_coroutine:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                req_tokens = _resolve_tokens(args, kwargs)
                if isinstance(limiter_inst, DualLimiter):
                    if blocking:
                        await limiter_inst.acquire_async(tokens=req_tokens, timeout=timeout)
                    else:
                        if not limiter_inst.try_acquire(tokens=req_tokens):
                            raise RateLimitExceeded("Dual budget rate limit exceeded.")
                else:
                    if blocking:
                        await limiter_inst.acquire_async(tokens=req_tokens, timeout=timeout)
                    else:
                        if not limiter_inst.try_acquire(tokens=req_tokens):
                            raise RateLimitExceeded("Rate limit exceeded.")
                return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                req_tokens = _resolve_tokens(args, kwargs)
                if isinstance(limiter_inst, DualLimiter):
                    if blocking:
                        limiter_inst.acquire_sync(tokens=req_tokens, timeout=timeout)
                    else:
                        if not limiter_inst.try_acquire(tokens=req_tokens):
                            raise RateLimitExceeded("Dual budget rate limit exceeded.")
                else:
                    if blocking:
                        limiter_inst.acquire_sync(tokens=req_tokens, timeout=timeout)
                    else:
                        if not limiter_inst.try_acquire(tokens=req_tokens):
                            raise RateLimitExceeded("Rate limit exceeded.")
                return fn(*args, **kwargs)

            return sync_wrapper  # type: ignore

    return decorator
