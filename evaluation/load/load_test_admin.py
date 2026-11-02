"""Load test for the Stage-2/4 administrator-confirmation endpoint (Stage
4's "Administrator confirmation functionality" requirement).

Seeds N reservations directly in the DB with status='pending_admin_approval'
(bypassing the chat flow for speed), then fires concurrent decision requests
at a running `app.main` instance's /admin/reservations/{id}/decision
endpoint -- exercising the orchestrator graph's resume path (and its
self-healing re-escalation) under concurrent admins/requests.

By default, the confirmed-reservation rows this writes (name prefixed
"LoadTest") are scrubbed from the output file afterwards; pass --keep-data
to leave them.

Usage:
    uvicorn app.main:app &
    uvicorn mcp_server.app:app --port 8001 &
    python -m evaluation.load.load_test_admin --total 20 --concurrency 10
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import httpx

from app.database import dynamic_service
from evaluation.load._utils import cleanup_lines_with_prefix, summarize_latencies

_NAME_PREFIX = "LoadTest Admin"


def _seed_reservations(total: int) -> list[int]:
    ids = []
    for i in range(total):
        reservation_id = dynamic_service.create_reservation(
            first_name=_NAME_PREFIX,
            last_name=str(i),
            car_number=f"LT-{i:04d}",
            start_time=datetime.utcnow() + timedelta(days=60),
            end_time=datetime.utcnow() + timedelta(days=60, hours=4),
            status="pending_admin_approval",
        )
        ids.append(reservation_id)
    return ids


def _decide(client: httpx.Client, base_url: str, reservation_id: int, decision: str) -> tuple[bool, float]:
    start = time.perf_counter()
    try:
        response = client.post(
            f"{base_url}/admin/reservations/{reservation_id}/decision",
            json={"decision": decision},
            timeout=15,
        )
        ok = response.status_code == 200
    except httpx.HTTPError:
        ok = False
    return ok, time.perf_counter() - start


def run(base_url: str = "http://localhost:8000", total: int = 20, concurrency: int = 10, keep_data: bool = False) -> dict:
    reservation_ids = _seed_reservations(total)

    wall_clock_start = time.perf_counter()
    results = []
    # Shared client: see the comment in load_test_chatbot.py for why a
    # fresh httpx.post() per call would measure client-side overhead, not
    # the admin endpoint's actual concurrent-decision performance.
    with httpx.Client() as client, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_decide, client, base_url, reservation_id, "approved" if i % 2 == 0 else "rejected")
            for i, reservation_id in enumerate(reservation_ids)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    wall_clock = time.perf_counter() - wall_clock_start

    latencies = [latency for ok, latency in results if ok]
    failed = total - len(latencies)

    report = {
        "total_decisions": total,
        "concurrency": concurrency,
        "succeeded": len(latencies),
        "failed": failed,
        "wall_clock_seconds": round(wall_clock, 3),
        "throughput_req_per_sec": round(total / wall_clock, 2) if wall_clock > 0 else None,
        **summarize_latencies(latencies),
    }

    if not keep_data:
        report["lines_cleaned_up"] = cleanup_lines_with_prefix(_NAME_PREFIX)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test the admin confirmation endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--keep-data", action="store_true", help="Don't scrub the test rows afterwards.")
    args = parser.parse_args()
    print(run(base_url=args.base_url, total=args.total, concurrency=args.concurrency, keep_data=args.keep_data))
