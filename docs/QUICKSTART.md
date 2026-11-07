# Quickstart Guide

Get up and running with **BurstGate** in less than 2 minutes.

## Installation

```bash
pip install burstgate
```

Zero external dependencies required. Built purely with the Python standard library.

---

## 1. Basic Rate Limiting

```python
from burstgate import RateLimiter

# 10 requests per second with burst up to 20
limiter = RateLimiter(limit=10, period=1.0, burst=20)

with limiter.acquire():
    print("Action executed within rate limits!")
```

---

## 2. Asynchronous Usage

```python
import asyncio
from burstgate import RateLimiter

limiter = RateLimiter(limit=50, period=1.0)

async def main():
    async with limiter.acquire(tokens=1):
        await asyncio.sleep(0.01)

asyncio.run(main())
```

---

## 3. LLM Dual-Budget Rate Limiting (RPM + TPM)

```python
import asyncio
from burstgate import DualLimiter, estimate_tokens

limiter = DualLimiter(rpm=60, tpm=30000)

async def call_llm(prompt: str):
    est_tokens = estimate_tokens(prompt)
    async with limiter.acquire(requests=1, tokens=est_tokens) as ticket:
        # response = await openai.chat.completions.create(...)
        # ticket.adjust(response.usage.total_tokens)
        pass
```

---

## 4. Multi-Process Sharing Without Redis

```python
from burstgate import RateLimiter, SQLiteStorage

# Multiple Gunicorn/Uvicorn workers can share this exact file
storage = SQLiteStorage("rate_limits.sqlite3")
limiter = RateLimiter(limit=100, period=1.0, storage=storage)

with limiter.acquire():
    # Coordinated across all OS worker processes!
    pass
```

---

## 5. CLI Tools

```bash
# Display system info
burstgate info

# Run benchmark
burstgate benchmark

# Simulate an LLM workload
burstgate simulate --rpm 60 --tpm 10000 --requests 10
```
