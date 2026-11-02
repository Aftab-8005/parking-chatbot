"""Shared helpers for the load-test scripts in this package."""

from __future__ import annotations

import statistics
from pathlib import Path

CONFIRMED_RESERVATIONS_FILE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "reservations" / "confirmed_reservations.txt"
)


def summarize_latencies(latencies: list[float]) -> dict:
    if not latencies:
        return {"p50_seconds": None, "p95_seconds": None, "max_seconds": None}
    ordered = sorted(latencies)
    p95_index = max(int(len(ordered) * 0.95) - 1, 0)
    return {
        "p50_seconds": round(statistics.median(ordered), 4),
        "p95_seconds": round(ordered[p95_index], 4),
        "max_seconds": round(max(ordered), 4),
    }


def count_lines(path: Path = CONFIRMED_RESERVATIONS_FILE) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())


def cleanup_lines_with_prefix(prefix: str, path: Path = CONFIRMED_RESERVATIONS_FILE) -> int:
    """Remove lines from the confirmed-reservations file whose Name field
    starts with `prefix` (used to scrub rows this load test wrote). Returns
    the number of lines removed."""
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith(prefix)]
    removed = len(lines) - len(kept)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed
