"""
Command Line Interface for BurstGate.

Provides benchmarking, simulation, and diagnostic inspection tools.
"""

from __future__ import annotations

import argparse
import sys
import time

from burstgate import __version__
from burstgate.algorithms.adaptive import AdaptiveLimiter
from burstgate.algorithms.leaky_bucket import LeakyBucket
from burstgate.algorithms.sliding_window import SlidingWindow
from burstgate.algorithms.token_bucket import TokenBucket
from burstgate.limiter.dual_limiter import DualLimiter
from burstgate.limiter.rate_limiter import RateLimiter
from burstgate.storage.memory import MemoryStorage
from burstgate.storage.sqlite import SQLiteStorage


def cmd_info(args: argparse.Namespace) -> int:
    print(f"BurstGate v{__version__} - High-Performance Resilient Rate Limiting Toolkit")
    print("=" * 68)
    print("Supported Algorithms:")
    print("  * Token Bucket (TokenBucket)        - Microsecond-precision refill & bursts")
    print("  * Sliding Window (SlidingWindow)    - Accurate rolling time-window without edge spikes")
    print("  * Leaky Bucket (LeakyBucket)        - Strict outflow smoothing & traffic shaping")
    print("  * Adaptive (AdaptiveLimiter)        - Latency-guided dynamic concurrency control")
    print("\nAI / LLM Dual Budgeting:")
    print("  * DualLimiter                       - Atomic RPM (Requests) & TPM (Tokens) control")
    print("  * DualTicket                        - Dynamic post-call token adjustment & refund")
    print("\nStorage Backends:")
    print("  * MemoryStorage                     - Fast thread-safe in-memory (> 1M ops/sec)")
    print("  * SQLiteStorage                     - Zero-dependency WAL-mode multi-process backend")
    print("=" * 68)
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    count = args.iterations
    print(f"Running BurstGate Micro-Benchmarks ({count:,} iterations each)...\n")

    # 1. TokenBucket + MemoryStorage
    tb = TokenBucket(rate=1_000_000, capacity=1_000_000)
    start = time.perf_counter()
    for _ in range(count):
        tb.consume(1.0)
    dur = time.perf_counter() - start
    ops_sec = count / dur if dur > 0 else 0
    print(f"[*] TokenBucket (Memory):    {dur:.4f}s  -->  {ops_sec:,.0f} ops/sec")

    # 2. SlidingWindow + MemoryStorage
    sw = SlidingWindow(limit=1_000_000, window_size=60.0)
    start = time.perf_counter()
    for _ in range(count):
        sw.consume(1.0)
    dur = time.perf_counter() - start
    ops_sec = count / dur if dur > 0 else 0
    print(f"[*] SlidingWindow (Memory):  {dur:.4f}s  -->  {ops_sec:,.0f} ops/sec")

    # 3. LeakyBucket + MemoryStorage
    lb = LeakyBucket(rate=1_000_000, capacity=1_000_000)
    start = time.perf_counter()
    for _ in range(count):
        lb.consume(1.0)
    dur = time.perf_counter() - start
    ops_sec = count / dur if dur > 0 else 0
    print(f"[*] LeakyBucket (Memory):    {dur:.4f}s  -->  {ops_sec:,.0f} ops/sec")

    # 4. DualLimiter
    dl = DualLimiter(rpm=60_000_000, tpm=60_000_000)
    start = time.perf_counter()
    for _ in range(count):
        dl.try_acquire(requests=1, tokens=10)
    dur = time.perf_counter() - start
    ops_sec = count / dur if dur > 0 else 0
    print(f"[*] DualLimiter (Memory):    {dur:.4f}s  -->  {ops_sec:,.0f} ops/sec")

    # 5. SQLiteStorage (lower count for disk I/O test)
    sqlite_count = min(count, 1000)
    db_file = "_bench_burstgate.sqlite3"
    try:
        sql_storage = SQLiteStorage(db_path=db_file)
        tb_sql = TokenBucket(rate=10000, capacity=10000, storage=sql_storage)
        start = time.perf_counter()
        for _ in range(sqlite_count):
            tb_sql.consume(1.0)
        dur = time.perf_counter() - start
        ops_sec = sqlite_count / dur if dur > 0 else 0
        print(f"[*] SQLiteStorage (WAL mode):{dur:.4f}s  -->  {ops_sec:,.0f} ops/sec ({sqlite_count:,} writes)")
        sql_storage.close()
    finally:
        import os
        for f in [db_file, f"{db_file}-wal", f"{db_file}-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    print("\nBenchmark completed successfully.")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    rpm = args.rpm
    tpm = args.tpm
    requests_to_run = args.requests

    print(f"Simulating LLM Workload: {requests_to_run} requests under RPM={rpm}, TPM={tpm}...\n")
    limiter = DualLimiter(rpm=rpm, tpm=tpm)

    start_time = time.time()
    total_tokens = 0

    for i in range(1, requests_to_run + 1):
        # Vary token size: 50 to 250 tokens
        tokens = 50 + (i * 20) % 200
        total_tokens += tokens
        wait = limiter.calculate_wait_time(requests=1, tokens=tokens)
        status = "ACQUIRED" if limiter.try_acquire(requests=1, tokens=tokens) else f"WAIT {wait:.2f}s"
        print(f"  Request #{i:02d} | Tokens: {tokens:3d} | Status: {status}")

    elapsed = time.time() - start_time
    print(f"\nSimulation finished in {elapsed:.3f}s. Total simulated tokens: {total_tokens:,}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="burstgate",
        description="BurstGate - High-performance resilient rate limiting and LLM traffic shaping CLI.",
    )
    parser.add_argument("--version", "-v", action="version", version=f"burstgate {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # info
    subparsers.add_parser("info", help="Display BurstGate architecture and algorithms.")

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run rate limiter throughput micro-benchmarks.")
    p_bench.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=100_000,
        help="Number of iterations for in-memory tests (default: 100,000).",
    )

    # simulate
    p_sim = subparsers.add_parser("simulate", help="Simulate LLM rate limiting workload.")
    p_sim.add_argument("--rpm", type=float, default=60, help="Requests Per Minute (default: 60)")
    p_sim.add_argument("--tpm", type=float, default=5000, help="Tokens Per Minute (default: 5000)")
    p_sim.add_argument("--requests", type=int, default=15, help="Number of simulated requests (default: 15)")

    args = parser.parse_args()

    if args.command == "info" or not args.command:
        return cmd_info(args)
    elif args.command == "benchmark":
        return cmd_benchmark(args)
    elif args.command == "simulate":
        return cmd_simulate(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
