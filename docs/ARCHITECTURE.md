# BurstGate Architecture & Engineering Design

BurstGate is a resilient, zero-dependency rate limiting, dual-resource token budgeting, and adaptive concurrency control engine for Python 3.10+.

```
                             +------------------------+
                             |   BurstGate Client     |
                             |  (Sync, Async, Decor)  |
                             +-----------+------------+
                                         |
                                         v
                             +------------------------+
                             |   Unified Limiter /    |
                             |      DualLimiter       |
                             +-----------+------------+
                                         |
            +----------------------------+----------------------------+
            |                            |                            |
            v                            v                            v
   +------------------+         +------------------+         +------------------+
   |   TokenBucket    |         |  SlidingWindow   |         |   LeakyBucket    |
   | (Continuous Fill)|         | (Sub-Intervals)  |         | (Outflow Shaper) |
   +--------+---------+         +--------+---------+         +--------+---------+
            |                            |                            |
            +----------------------------+----------------------------+
                                         |
                                         v
                             +------------------------+
                             |     Storage Layer      |
                             |  (Memory / SQLite WAL) |
                             +------------------------+
```

## Core Primitives

### 1. Token Bucket (`TokenBucket`)
- **Concept:** Continuous microsecond-precision token generation.
- **Refill Formula:** $\text{tokens}_{\text{new}} = \min(\text{capacity}, \text{tokens}_{\text{old}} + \Delta t \times \text{rate})$
- **Properties:** Allows sudden burst allowance up to `capacity` while strictly respecting average throughput `rate`.

### 2. Sliding Window Counter (`SlidingWindow`)
- **Concept:** Sub-interval granular bucket grouping within a rolling time window $W$.
- **Spike Immunity:** Completely eliminates boundary edge spikes found in fixed window counters (e.g. 100 requests at 00:59 followed by 100 requests at 01:00).
- **Time Complexity:** $O(B)$ where $B$ is the number of sub-buckets (typically $\le 20$).

### 3. Leaky Bucket (`LeakyBucket`)
- **Concept:** Strict FIFO queue emulation where operations leak out at a steady rate.
- **Traffic Shaping:** Enforces uniform inter-request latency, preventing downstream saturation.

### 4. Adaptive Concurrency Limiter (`AdaptiveLimiter`)
- **Inspiration:** TCP Vegas & Netflix Concurrency Limits.
- **Dynamic Control:** Automatically computes baseline round-trip latency ($\text{RTT}_{\min}$). When actual latency stays within tolerance, concurrency increases additively ($\Delta L = 1 / L$). When latency degrades or errors (429/503) occur, backoff scales down aggressively ($L = L \times \beta$).

### 5. Dual-Resource Budgeting (`DualLimiter`)
- **LLM Specific:** Coordinates two orthogonal constraints simultaneously:
  - Requests Per Minute (RPM)
  - Tokens Per Minute (TPM)
- **Atomic Acquisition:** Either both budgets pass, or neither is deducted, eliminating partial failures.
- **Dynamic Tickets:** The `DualTicket` allows callers to estimate prompt token cost upfront and refund or debit the exact difference after the LLM provider returns token statistics.

## Storage Backends

| Backend | Scope | Thread-Safe | Async-Safe | Multi-Process | External Deps |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `MemoryStorage` | In-process | Yes (RLock) | Yes | No | None |
| `SQLiteStorage` | Inter-process | Yes | Yes | Yes (WAL mode) | None |
