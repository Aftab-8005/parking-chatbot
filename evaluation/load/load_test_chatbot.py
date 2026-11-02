"""Load test for the Stage-1 chatbot in interactive dialogue mode (Stage 4's
"Conduct load tests ... Chatbot in interactive dialogue mode" requirement).

Fires concurrent /chat requests -- one independent session per simulated
user, asking dynamic-info questions (hours/prices/availability), which is
safe to repeat since it never writes to the database -- at a running
`app.main` instance and reports latency + throughput.

Usage:
    uvicorn app.main:app &          # have the API running first
    python -m evaluation.load.load_test_chatbot --total 200 --concurrency 20
"""

from __future__ import annotations

import argparse
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from evaluation.load._utils import summarize_latencies

_QUESTIONS = [
    "What are your working hours?",
    "How many parking spaces are available?",
    "What is the price per hour?",
]


def _one_turn(client: httpx.Client, base_url: str, question: str) -> tuple[bool, float]:
    session_id = str(uuid.uuid4())
    start = time.perf_counter()
    try:
        response = client.post(
            f"{base_url}/chat", json={"session_id": session_id, "message": question}, timeout=15
        )
        ok = response.status_code == 200
    except httpx.HTTPError:
        ok = False
    return ok, time.perf_counter() - start


def run(base_url: str = "http://localhost:8000", total: int = 100, concurrency: int = 20) -> dict:
    wall_clock_start = time.perf_counter()
    results = []
    # A shared httpx.Client (thread-safe, connection-pooling) is essential
    # here: calling the module-level httpx.post() per request creates a
    # brand-new client (full connection pool + TLS setup) every time, which
    # under concurrency measures client-side overhead, not server latency.
    with httpx.Client() as client, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_one_turn, client, base_url, _QUESTIONS[i % len(_QUESTIONS)]) for i in range(total)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    wall_clock = time.perf_counter() - wall_clock_start

    latencies = [latency for ok, latency in results if ok]
    failed = total - len(latencies)

    return {
        "total_requests": total,
        "concurrency": concurrency,
        "succeeded": len(latencies),
        "failed": failed,
        "wall_clock_seconds": round(wall_clock, 3),
        "throughput_req_per_sec": round(total / wall_clock, 2) if wall_clock > 0 else None,
        **summarize_latencies(latencies),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test the chatbot's /chat endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--total", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    print(run(base_url=args.base_url, total=args.total, concurrency=args.concurrency))
