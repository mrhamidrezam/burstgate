"""
Adaptive Concurrency Control Example.
Dynamically scales concurrency up when healthy and scales down when latency spikes.
"""

import random
import time
from burstgate import AdaptiveLimiter

limiter = AdaptiveLimiter(min_limit=2, max_limit=15, initial_limit=4)

print("Starting adaptive latency simulation...")
for step in range(1, 16):
    # Simulate fluctuating downstream latency
    simulated_rtt = random.uniform(0.015, 0.035) if step <= 8 else random.uniform(0.080, 0.150)

    try:
        with limiter.probe():
            time.sleep(simulated_rtt)
        status = "Healthy" if simulated_rtt < 0.050 else "High Latency"
        print(f"Step {step:02d} | RTT: {simulated_rtt*1000:5.1f}ms | Limit: {limiter.current_limit:2d} | Status: {status}")
    except RuntimeError:
        print(f"Step {step:02d} | Throttled by adaptive limiter!")
