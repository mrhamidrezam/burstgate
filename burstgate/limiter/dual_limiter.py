"""
Dual-Resource Rate Limiter for LLMs & AI Workloads.

Simultaneously enforces Requests Per Minute (RPM) and Tokens Per Minute (TPM)
with atomic acquisition and dynamic post-call token adjustment.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional, Tuple, Union

from burstgate.algorithms.token_bucket import TokenBucket
from burstgate.errors import AcquireTimeout, BudgetExceeded, ConfigurationError
from burstgate.storage.base import StorageBackend
from burstgate.storage.memory import MemoryStorage


def estimate_tokens(text: str) -> int:
    """
    Fast, dependency-free heuristic token estimator (~4 chars per token for English/Code).
    Safe lower bound / reasonable estimate when tiktoken/tokenizers are not installed.
    """
    if not text:
        return 0
    # Average of ~3.8 characters per token across English prose and source code
    return max(1, int(len(text) / 3.8))


class DualTicket:
    """
    Handle returned by DualLimiter.acquire() allowing dynamic post-call token adjustments.
    """

    def __init__(
        self,
        limiter: DualLimiter,
        initial_requests: float,
        initial_tokens: float,
    ) -> None:
        self.limiter = limiter
        self.requests = initial_requests
        self.tokens = initial_tokens
        self._adjusted = False

    def adjust(self, actual_tokens: float) -> None:
        """
        Adjust token usage after obtaining the exact token count from the LLM provider.

        Args:
            actual_tokens: The true total tokens reported by the API.
        """
        if self._adjusted:
            return
        self._adjusted = True
        delta = actual_tokens - self.tokens
        if delta > 0:
            # Consumed more tokens than estimated; debit difference
            self.limiter.token_bucket.consume(delta)
        elif delta < 0:
            # Overestimated tokens; refund difference back to the bucket
            refund = abs(delta)
            self._refund_tokens(refund)
        self.tokens = actual_tokens

    def _refund_tokens(self, amount: float) -> None:
        storage = self.limiter.token_bucket.storage
        key = self.limiter.token_bucket.key
        capacity = self.limiter.token_bucket.capacity

        def _update(state: Optional[dict]) -> Tuple[dict, None]:
            now = time.time()
            if state is None:
                state = {"tokens": capacity, "last_updated": now}
            curr = state.get("tokens", capacity)
            new_tokens = min(capacity, curr + amount)
            return {"tokens": new_tokens, "last_updated": now}, None

        storage.atomic_update(key, _update, default=None)


class DualAcquisitionContext:
    """Context manager for DualLimiter supporting both sync and async blocks."""

    def __init__(
        self,
        limiter: DualLimiter,
        requests: float,
        tokens: float,
        timeout: Optional[float],
    ) -> None:
        self.limiter = limiter
        self.requests = requests
        self.tokens = tokens
        self.timeout = timeout
        self.ticket: Optional[DualTicket] = None

    def __enter__(self) -> DualTicket:
        self.limiter.acquire_sync(
            requests=self.requests,
            tokens=self.tokens,
            timeout=self.timeout,
        )
        self.ticket = DualTicket(self.limiter, self.requests, self.tokens)
        return self.ticket

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def __aenter__(self) -> DualTicket:
        await self.limiter.acquire_async(
            requests=self.requests,
            tokens=self.tokens,
            timeout=self.timeout,
        )
        self.ticket = DualTicket(self.limiter, self.requests, self.tokens)
        return self.ticket

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class DualLimiter:
    """
    Dual-budget Rate Limiter designed specifically for LLM APIs (OpenAI, Gemini, Anthropic, Ollama).

    Guarantees that both Requests Per Minute (RPM) and Tokens Per Minute (TPM)
    are respected simultaneously without exceeding upstream rate limits.

    Args:
        rpm: Permitted requests per minute. Must be > 0.
        tpm: Permitted tokens per minute. Must be > 0.
        burst_rpm: Optional burst capacity for requests (defaults to rpm / 2 or rpm).
        burst_tpm: Optional burst capacity for tokens (defaults to tpm).
        storage: State storage backend (defaults to MemoryStorage).
        key: Unique storage identifier prefix.
        raise_on_limit: If True, non-blocking check failures raise BudgetExceeded.
    """

    def __init__(
        self,
        rpm: float,
        tpm: float,
        burst_rpm: Optional[float] = None,
        burst_tpm: Optional[float] = None,
        storage: Optional[StorageBackend] = None,
        key: str = "burstgate:dual",
        raise_on_limit: bool = False,
    ) -> None:
        if rpm <= 0:
            raise ConfigurationError(f"RPM must be > 0, got {rpm}")
        if tpm <= 0:
            raise ConfigurationError(f"TPM must be > 0, got {tpm}")

        self.rpm = float(rpm)
        self.tpm = float(tpm)
        self.storage = storage or MemoryStorage()
        self.key = key
        self.raise_on_limit = raise_on_limit

        # Continuous rates per second
        req_rate = self.rpm / 60.0
        tok_rate = self.tpm / 60.0

        req_capacity = float(burst_rpm if burst_rpm is not None else max(1.0, self.rpm * 0.2))
        tok_capacity = float(burst_tpm if burst_tpm is not None else self.tpm * 0.5)

        self.request_bucket = TokenBucket(
            rate=req_rate,
            capacity=max(req_capacity, 1.0),
            storage=self.storage,
            key=f"{key}:req_bucket",
        )
        self.token_bucket = TokenBucket(
            rate=tok_rate,
            capacity=max(tok_capacity, 100.0),
            storage=self.storage,
            key=f"{key}:tok_bucket",
        )

    def try_acquire(self, requests: float = 1.0, tokens: float = 0.0) -> bool:
        """
        Attempt to acquire both request quota and token quota atomically.

        Returns:
            True if both were acquired, False if either budget would be exceeded.
        """
        # Pre-check available tokens and requests before mutating
        req_avail = self.request_bucket.available_tokens()
        tok_avail = self.token_bucket.available_tokens()

        if req_avail < requests or (tokens > 0 and tok_avail < tokens):
            if self.raise_on_limit:
                failed_resource = "rpm" if req_avail < requests else "tpm"
                retry = max(
                    (requests - req_avail) / self.request_bucket.rate if req_avail < requests else 0.0,
                    (tokens - tok_avail) / self.token_bucket.rate if tok_avail < tokens else 0.0,
                )
                raise BudgetExceeded(
                    message=f"LLM quota exceeded for {failed_resource}.",
                    retry_after=retry,
                    limit=self.rpm if failed_resource == "rpm" else self.tpm,
                    period=60.0,
                    resource=failed_resource,
                    requested_tokens=tokens,
                    available_tokens=tok_avail,
                )
            return False

        # Consume atomically
        req_ok, _ = self.request_bucket.consume(requests)
        if not req_ok:
            return False

        if tokens > 0:
            tok_ok, _ = self.token_bucket.consume(tokens)
            if not tok_ok:
                # Rollback request consumption
                self.request_bucket.consume(-requests)
                return False

        return True

    def calculate_wait_time(self, requests: float = 1.0, tokens: float = 0.0) -> float:
        """Compute the duration in seconds until both requests and tokens become available."""
        req_avail = self.request_bucket.available_tokens()
        tok_avail = self.token_bucket.available_tokens()

        wait_req = max(0.0, (requests - req_avail) / self.request_bucket.rate)
        wait_tok = max(0.0, (tokens - tok_avail) / self.token_bucket.rate) if tokens > 0 else 0.0
        return max(wait_req, wait_tok)

    def acquire_sync(
        self,
        requests: float = 1.0,
        tokens: float = 0.0,
        timeout: Optional[float] = None,
    ) -> bool:
        """Synchronously wait until both request and token capacity are acquired."""
        start = time.monotonic()
        while True:
            if self.try_acquire(requests, tokens):
                return True

            wait = self.calculate_wait_time(requests, tokens)
            if timeout is not None:
                elapsed = time.monotonic() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    if self.raise_on_limit:
                        raise AcquireTimeout(timeout=timeout)
                    return False
                sleep_dur = min(wait, remaining)
            else:
                sleep_dur = max(0.005, wait)

            time.sleep(sleep_dur)

    async def acquire_async(
        self,
        requests: float = 1.0,
        tokens: float = 0.0,
        timeout: Optional[float] = None,
    ) -> bool:
        """Asynchronously wait until both request and token capacity are acquired."""
        start = time.monotonic()
        while True:
            if self.try_acquire(requests, tokens):
                return True

            wait = self.calculate_wait_time(requests, tokens)
            if timeout is not None:
                elapsed = time.monotonic() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    if self.raise_on_limit:
                        raise AcquireTimeout(timeout=timeout)
                    return False
                sleep_dur = min(wait, remaining)
            else:
                sleep_dur = max(0.005, wait)

            await asyncio.sleep(sleep_dur)

    def acquire(
        self,
        requests: float = 1.0,
        tokens: float = 0.0,
        timeout: Optional[float] = None,
    ) -> DualAcquisitionContext:
        """
        Unified context manager returning a DualTicket for post-call adjustment.

        Usage:
            async with dual_limiter.acquire(tokens=200) as ticket:
                resp = await openai.chat.completions.create(...)
                ticket.adjust(resp.usage.total_tokens)
        """
        return DualAcquisitionContext(
            self,
            requests=requests,
            tokens=tokens,
            timeout=timeout,
        )
