"""HTTP client for the Stage-3 MCP server (`mcp_server/app.py`).

Used by the orchestrator graph's `data_recording` node once an administrator
approves a reservation.
"""

from __future__ import annotations

import httpx

from app.config import settings


class MCPWriteError(RuntimeError):
    pass


def write_confirmed_reservation(name: str, car_number: str, period: str, approval_time: str) -> str:
    """Call the MCP server's `write_reservation` tool. Returns the line that
    was written. Raises `MCPWriteError` on any transport/HTTP failure."""
    url = f"{settings.mcp_base_url}/mcp/tools/write_reservation/call"
    headers = {"Authorization": f"Bearer {settings.mcp_api_key}"}
    payload = {"name": name, "car_number": car_number, "period": period, "approval_time": approval_time}

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MCPWriteError(f"Failed to write confirmed reservation via MCP server: {exc}") from exc

    return response.json()["line"]
