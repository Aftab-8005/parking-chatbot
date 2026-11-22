"""MCP client used by the LangGraph `store_via_mcp` node to call the
`save_confirmed_reservation` tool on the standalone MCP server.

Raises `McpUnavailableError` for any connectivity/timeout/tool-level failure
so the caller can apply the Stage-3 fallback (mark the reservation
`approved_pending_storage` instead of crashing).
"""

from __future__ import annotations

import logging
from datetime import datetime

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings

logger = logging.getLogger("parking_chatbot.mcp_client")


class McpUnavailableError(RuntimeError):
    """Raised when the MCP server cannot be reached or the tool call fails."""


async def _call_save_confirmed_reservation(
    request_id: str,
    name: str,
    car_number: str,
    period_start: datetime,
    period_end: datetime,
    approval_time: datetime,
    facility: str = "",
) -> dict:
    async with streamablehttp_client(settings.mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "save_confirmed_reservation",
                {
                    "token": settings.mcp_auth_token,
                    "request_id": request_id,
                    "name": name,
                    "car_number": car_number,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "approval_time": approval_time.isoformat(),
                    "facility": facility,
                },
            )
            if result.isError:
                message = result.content[0].text if result.content else "MCP tool call failed."
                raise McpUnavailableError(message)
            return {"stored": True}


def save_confirmed_reservation(
    request_id: str,
    name: str,
    car_number: str,
    period_start: datetime,
    period_end: datetime,
    approval_time: datetime,
    facility: str = "",
) -> dict:
    """Synchronous wrapper around the async MCP tool call, with a timeout."""
    try:
        return anyio.run(
            _run_with_timeout, request_id, name, car_number, period_start, period_end, approval_time, facility
        )
    except McpUnavailableError:
        raise
    except Exception as exc:  # connection refused, timeout, protocol error, etc.
        logger.warning("MCP server unavailable while storing request_id=%s: %s", request_id, exc)
        raise McpUnavailableError(str(exc)) from exc


async def _run_with_timeout(
    request_id: str,
    name: str,
    car_number: str,
    period_start: datetime,
    period_end: datetime,
    approval_time: datetime,
    facility: str = "",
) -> dict:
    with anyio.fail_after(settings.mcp_request_timeout_seconds):
        return await _call_save_confirmed_reservation(
            request_id, name, car_number, period_start, period_end, approval_time, facility
        )
