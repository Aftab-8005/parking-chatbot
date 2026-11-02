"""Load test for the Stage-3 MCP server (Stage 4's "MCP server recording and
storage process" requirement).

Fires concurrent write_reservation tool calls at a running `mcp_server.app`
instance and checks two things: latency/throughput, and file integrity --
that the file-lock actually serializes concurrent writers so exactly one
line per successful call ends up in the file, with no interleaved/corrupted
rows.

By default, the rows this script writes (name prefixed "LoadTest") are
scrubbed from the output file afterwards; pass --keep-data to leave them.

Usage:
    uvicorn mcp_server.app:app --port 8001 &
    python -m evaluation.load.load_test_mcp --total 200 --concurrency 20
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from app.config import settings
from evaluation.load._utils import cleanup_lines_with_prefix, count_lines, summarize_latencies

_NAME_PREFIX = "LoadTest User"


def _call(client: httpx.Client, i: int) -> tuple[bool, float]:
    url = f"{settings.mcp_base_url}/mcp/tools/write_reservation/call"
    headers = {"Authorization": f"Bearer {settings.mcp_api_key}"}
    payload = {
        "name": f"{_NAME_PREFIX} {i}",
        "car_number": f"LT-{i:04d}",
        "period": "2026-12-31 00:00 - 2026-12-31 01:00",
        "approval_time": "load-test",
    }
    start = time.perf_counter()
    try:
        response = client.post(url, json=payload, headers=headers, timeout=10)
        ok = response.status_code == 200
    except httpx.HTTPError:
        ok = False
    return ok, time.perf_counter() - start


def run(total: int = 100, concurrency: int = 20, keep_data: bool = False) -> dict:
    lines_before = count_lines()

    wall_clock_start = time.perf_counter()
    results = []
    # Shared client: see the comment in load_test_chatbot.py for why a
    # fresh httpx.post() per call would measure client-side overhead, not
    # the MCP server's actual concurrent-write performance.
    with httpx.Client() as client, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_call, client, i) for i in range(total)]
        for future in as_completed(futures):
            results.append(future.result())
    wall_clock = time.perf_counter() - wall_clock_start

    latencies = [latency for ok, latency in results if ok]
    failed = total - len(latencies)
    lines_after = count_lines()
    lines_added = lines_after - lines_before

    report = {
        "total_requests": total,
        "concurrency": concurrency,
        "succeeded": len(latencies),
        "failed": failed,
        "wall_clock_seconds": round(wall_clock, 3),
        "throughput_req_per_sec": round(total / wall_clock, 2) if wall_clock > 0 else None,
        "lines_added_to_file": lines_added,
        "file_integrity_ok": lines_added == len(latencies),
        **summarize_latencies(latencies),
    }

    if not keep_data:
        report["lines_cleaned_up"] = cleanup_lines_with_prefix(_NAME_PREFIX)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test the MCP server's write_reservation tool.")
    parser.add_argument("--total", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--keep-data", action="store_true", help="Don't scrub the test rows afterwards.")
    args = parser.parse_args()
    print(run(total=args.total, concurrency=args.concurrency, keep_data=args.keep_data))
