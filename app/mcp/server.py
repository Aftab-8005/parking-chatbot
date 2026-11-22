"""MCP server for Stage 3: persists administrator-approved reservations.

Exposes a single tool, `save_confirmed_reservation`, over the MCP
streamable-http transport. Run standalone:

    python -m app.mcp.server

The tool only ever writes to the single, configured reservations file
(`settings.reservations_file_path`) -- it never accepts a caller-supplied
path, which is what rules out path traversal / arbitrary file writes.
"""

import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.config import settings

logger = logging.getLogger("parking_chatbot.mcp")

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,99}$")
_CAR_NUMBER_RE = re.compile(r"^[A-Za-z0-9\-]{2,20}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,36}$")
_FACILITY_RE = re.compile(r"^[A-Za-z0-9 .,'\-]{0,60}$")

_write_lock = threading.Lock()

_BASE_DIR = Path(__file__).resolve().parents[2]


class ReservationValidationError(ValueError):
    """Raised when the MCP tool receives invalid/unauthorized input."""


def _resolve_reservations_path() -> Path:
    """Resolve the configured reservations file, refusing to write anywhere
    outside the project's `data/` directory even if misconfigured."""
    path = (_BASE_DIR / settings.reservations_file_path).resolve()
    allowed_root = (_BASE_DIR / "data").resolve()
    if allowed_root not in path.parents and path != allowed_root:
        raise ReservationValidationError("Reservation storage path is outside the allowed data directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _authorize(token: str) -> None:
    if not token or token != settings.mcp_auth_token:
        raise ReservationValidationError("Unauthorized: invalid MCP access token.")


def _validate_facility(value: str) -> str:
    value = (value or "").strip()
    if not _FACILITY_RE.match(value):
        raise ReservationValidationError("Invalid facility name.")
    return value


def _validate_reservation_fields(
    name: str, car_number: str, period_start: str, period_end: str, approval_time: str, request_id: str
) -> tuple[str, str, datetime, datetime, datetime, str]:
    name = (name or "").strip()
    car_number = (car_number or "").strip().upper()
    request_id = (request_id or "").strip()

    if not _NAME_RE.match(name):
        raise ReservationValidationError("Invalid name.")
    if not _CAR_NUMBER_RE.match(car_number):
        raise ReservationValidationError("Invalid car number.")
    if not _REQUEST_ID_RE.match(request_id):
        raise ReservationValidationError("Invalid request id.")

    try:
        start_dt = datetime.fromisoformat(period_start)
        end_dt = datetime.fromisoformat(period_end)
        approved_dt = datetime.fromisoformat(approval_time)
    except (TypeError, ValueError) as exc:
        raise ReservationValidationError("Invalid date/time format; expected ISO-8601.") from exc

    if end_dt <= start_dt:
        raise ReservationValidationError("Reservation end time must be after start time.")

    return name, car_number, start_dt, end_dt, approved_dt, request_id


_DELIMITER_RE = re.compile(r"[\r\n|]")


def _append_reservation_line(
    name: str,
    car_number: str,
    start_dt: datetime,
    end_dt: datetime,
    approved_dt: datetime,
    facility: str = "",
) -> str:
    period = f"{start_dt.strftime('%Y-%m-%d %H:%M')}-{end_dt.strftime('%H:%M')}"
    # Defense-in-depth: even though the regex validators above already reject
    # "|"/newlines in name/car_number, strip them again here so a validator
    # change elsewhere can never let a value escape the single-line record format.
    safe_name = _DELIMITER_RE.sub(" ", name).strip()
    safe_car_number = _DELIMITER_RE.sub(" ", car_number).strip()
    safe_facility = _DELIMITER_RE.sub(" ", facility).strip()
    line = f"{safe_name} | {safe_car_number} | {period} | {approved_dt.strftime('%Y-%m-%d %H:%M')}"
    if safe_facility:
        line += f" | {safe_facility}"

    path = _resolve_reservations_path()
    with _write_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return line


mcp_app = FastMCP(
    "parking-reservation-mcp",
    host=settings.mcp_host,
    port=settings.mcp_port,
    # The client opens one connection per tool call and then disconnects
    # (app/mcp/client.py), so there's no reason to keep server-side session
    # state between calls. stateless_http also avoids a benign-but-noisy
    # ClosedResourceError the stateful session manager logs on teardown when
    # a short-lived client disconnects right after its one request.
    stateless_http=True,
)


@mcp_app.tool()
def save_confirmed_reservation(
    token: str,
    request_id: str,
    name: str,
    car_number: str,
    period_start: str,
    period_end: str,
    approval_time: str,
    facility: str = "",
) -> dict:
    """Persist an administrator-approved parking reservation.

    Args:
        token: Shared MCP access token (see MCP_AUTH_TOKEN).
        request_id: The admin-request reference this reservation was approved under.
        name: Full name of the person the reservation is for.
        car_number: License plate number.
        period_start: ISO-8601 reservation start time.
        period_end: ISO-8601 reservation end time.
        approval_time: ISO-8601 time the administrator approved the request.
        facility: Display name of the parking facility the reservation is for (optional).

    Returns:
        {"stored": True, "line": "<written line>"} on success.
    """
    try:
        _authorize(token)
        name_v, car_v, start_dt, end_dt, approved_dt, request_id_v = _validate_reservation_fields(
            name, car_number, period_start, period_end, approval_time, request_id
        )
        facility_v = _validate_facility(facility)
        line = _append_reservation_line(name_v, car_v, start_dt, end_dt, approved_dt, facility_v)
    except ReservationValidationError as exc:
        logger.warning("Rejected save_confirmed_reservation call: %s", exc)
        raise

    logger.info("Stored confirmed reservation request_id=%s", request_id_v)
    return {"stored": True, "line": line}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting MCP server on %s:%s (from settings)", settings.mcp_host, settings.mcp_port)
    mcp_app.run(transport="streamable-http")
