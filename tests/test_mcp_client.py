from datetime import datetime

import pytest

from app.mcp import client as mcp_client


def test_save_confirmed_reservation_raises_mcp_unavailable_when_server_down(monkeypatch):
    monkeypatch.setattr(mcp_client.settings, "mcp_port", 1)  # nothing listens here
    monkeypatch.setattr(mcp_client.settings, "mcp_request_timeout_seconds", 0.5)

    with pytest.raises(mcp_client.McpUnavailableError):
        mcp_client.save_confirmed_reservation(
            request_id="req-12345678",
            name="Jane Doe",
            car_number="AB1234",
            period_start=datetime(2026, 11, 25, 10, 0),
            period_end=datetime(2026, 11, 25, 12, 0),
            approval_time=datetime(2026, 11, 22, 18, 30),
        )


def test_save_confirmed_reservation_wraps_tool_error(monkeypatch):
    async def fake_run_with_timeout(*args, **kwargs):
        raise mcp_client.McpUnavailableError("tool rejected input")

    monkeypatch.setattr(mcp_client, "_run_with_timeout", fake_run_with_timeout)

    with pytest.raises(mcp_client.McpUnavailableError):
        mcp_client.save_confirmed_reservation(
            request_id="req-12345678",
            name="Jane Doe",
            car_number="AB1234",
            period_start=datetime(2026, 11, 25, 10, 0),
            period_end=datetime(2026, 11, 25, 12, 0),
            approval_time=datetime(2026, 11, 22, 18, 30),
        )
