"""
Dual-Resource LLM Rate Limiting Example with BurstGate.
Demonstrates simultaneous RPM (Requests) and TPM (Tokens) control with post-call adjustment.
"""

import asyncio
from burstgate import DualLimiter, estimate_tokens

# Provider limits: 60 RPM and 30,000 TPM
llm_limiter = DualLimiter(rpm=60, tpm=30000, burst_rpm=10, burst_tpm=5000)


async def call_llm(prompt: str) -> dict:
    estimated_prompt_tokens = estimate_tokens(prompt)
    print(f"-> Submitting prompt (Estimated tokens: {estimated_prompt_tokens})...")

    # Acquire lock for 1 request and estimated tokens
    async with llm_limiter.acquire(requests=1, tokens=estimated_prompt_tokens) as ticket:
        # Simulate LLM API roundtrip
        await asyncio.sleep(0.05)
        simulated_response = {
            "text": "Paris is the capital of France.",
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        }

        # Dynamically adjust to exact usage returned by provider!
        ticket.adjust(actual_tokens=simulated_response["usage"]["total_tokens"])
        print(f"<- Received response. Adjusted actual tokens: {ticket.tokens}")
        return simulated_response


async def main():
    prompts = [
        "What is the capital of France?",
        "Explain quantum computing in simple terms.",
        "Write a Python function to compute Fibonacci numbers.",
    ]
    tasks = [call_llm(p) for p in prompts]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
