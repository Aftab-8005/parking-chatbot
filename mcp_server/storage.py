"""File-backed storage for confirmed parking reservations.

This is the "write to file" side of the MCP server (Stage 3): once an
administrator approves a reservation, the orchestrator graph calls the MCP
server's `write_reservation` tool, which appends a line to
`data/reservations/confirmed_reservations.txt` in the format:

    Name | Car Number | Reservation Period | Approval Time

Writes are append-only and serialized with a file lock so two concurrent
approvals can't interleave and corrupt a line.
"""

from __future__ import annotations

import re
from pathlib import Path

from filelock import FileLock

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "reservations"
OUTPUT_FILE = DATA_DIR / "confirmed_reservations.txt"
LOCK_FILE = DATA_DIR / ".confirmed_reservations.lock"

_MAX_FIELD_LENGTH = 200
_UNSAFE_CHARS_RE = re.compile(r"[\r\n|]")


class InvalidReservationFieldError(ValueError):
    pass


def _sanitize_field(name: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise InvalidReservationFieldError(f"'{name}' must not be empty.")
    if len(value) > _MAX_FIELD_LENGTH:
        raise InvalidReservationFieldError(f"'{name}' exceeds {_MAX_FIELD_LENGTH} characters.")
    # Strip the delimiter and newlines so a value can't inject an extra
    # record or escape the single-line "A | B | C | D" format.
    return _UNSAFE_CHARS_RE.sub(" ", value).strip()


def write_reservation(name: str, car_number: str, period: str, approval_time: str) -> str:
    """Validate and append one confirmed-reservation line.

    Returns the exact line written (useful for the API response / tests).
    Raises `InvalidReservationFieldError` if any field is empty or too long.
    """
    safe_name = _sanitize_field("name", name)
    safe_car_number = _sanitize_field("car_number", car_number)
    safe_period = _sanitize_field("period", period)
    safe_approval_time = _sanitize_field("approval_time", approval_time)

    line = f"{safe_name} | {safe_car_number} | {safe_period} | {safe_approval_time}"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(LOCK_FILE)):
        with OUTPUT_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return line
