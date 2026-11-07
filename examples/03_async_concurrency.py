"""
High-throughput Async Task Pooling with BurstGate.
"""

import asyncio
import time
from burstgate import RateLimiter

limiter = RateLimiter(limit=20, period=1.0, algorithm="sliding_window")


async def worker(worker_id: int):
    for i in range(3):
        async with limiter.acquire(tokens=1):
            now_str = time.strftime("%H:%M:%S")
            print(f"[{now_str}] Worker {worker_id} processed item {i}")
            await asyncio.sleep(0.02)


async def main():
    print("Spawning 10 concurrent async workers throttled by BurstGate...")
    start = time.perf_counter()
    await asyncio.gather(*(worker(w) for w in range(1, 11)))
    dur = time.perf_counter() - start
    print(f"All 30 items completed in {dur:.2f}s!")


if __name__ == "__main__":
    asyncio.run(main())
