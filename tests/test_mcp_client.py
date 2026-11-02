from unittest.mock import MagicMock

import httpx
import pytest

from app.mcp_client import client as mcp_client


def test_write_confirmed_reservation_returns_line_on_success(monkeypatch):
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"status": "written", "line": "Jane Doe | AB-1234 | p | t"}
    monkeypatch.setattr(mcp_client.httpx, "post", MagicMock(return_value=fake_response))

    line = mcp_client.write_confirmed_reservation("Jane Doe", "AB-1234", "p", "t")
    assert line == "Jane Doe | AB-1234 | p | t"


def test_write_confirmed_reservation_raises_mcp_write_error_on_http_failure(monkeypatch):
    monkeypatch.setattr(
        mcp_client.httpx, "post", MagicMock(side_effect=httpx.ConnectError("connection refused"))
    )

    with pytest.raises(mcp_client.MCPWriteError):
        mcp_client.write_confirmed_reservation("Jane Doe", "AB-1234", "p", "t")


def test_write_confirmed_reservation_sends_bearer_token(monkeypatch):
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"status": "written", "line": "x"}
    post_mock = MagicMock(return_value=fake_response)
    monkeypatch.setattr(mcp_client.httpx, "post", post_mock)
    monkeypatch.setattr(mcp_client.settings, "mcp_api_key", "secret-token")

    mcp_client.write_confirmed_reservation("Jane Doe", "AB-1234", "p", "t")

    _, kwargs = post_mock.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
