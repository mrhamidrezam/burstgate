"""
Basic Rate Limiting Example with BurstGate.
Demonstrates sync context manager, try_acquire, and algorithm choices.
"""

import time
from burstgate import RateLimiter

# Create a rate limiter: 5 requests per second, with burst up to 10
limiter = RateLimiter(limit=5, period=1.0, burst=10)

print("1. Using Context Manager (Auto-sleeping when limited):")
for i in range(1, 8):
    with limiter.acquire(tokens=1):
        print(f"   [{time.strftime('%H:%M:%S')}] Executed job #{i}")

print("\n2. Non-blocking Immediate Check:")
for i in range(1, 8):
    if limiter.try_acquire(tokens=2):
        print(f"   Permit granted for batch #{i}")
    else:
        wait = limiter.retry_after(tokens=2)
        print(f"   Rate limit reached for batch #{i}! Retry after {wait:.2f}s")
