from fastapi.testclient import TestClient

from mcp_server import app as mcp_app_module
from mcp_server.app import app

client = TestClient(app)


def test_call_tool_requires_valid_bearer_token():
    response = client.post(
        "/mcp/tools/write_reservation/call",
        json={"name": "Jane Doe", "car_number": "AB-1234", "period": "p", "approval_time": "t"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_call_tool_rejects_missing_token():
    response = client.post(
        "/mcp/tools/write_reservation/call",
        json={"name": "Jane Doe", "car_number": "AB-1234", "period": "p", "approval_time": "t"},
    )
    assert response.status_code == 401


def test_call_tool_writes_reservation_with_valid_token(monkeypatch):
    monkeypatch.setattr(mcp_app_module, "write_reservation", lambda **kwargs: "Jane Doe | AB-1234 | p | t")
    token = mcp_app_module.settings.mcp_api_key

    response = client.post(
        "/mcp/tools/write_reservation/call",
        json={"name": "Jane Doe", "car_number": "AB-1234", "period": "p", "approval_time": "t"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "written", "line": "Jane Doe | AB-1234 | p | t"}


def test_list_tools_returns_write_reservation_tool():
    token = mcp_app_module.settings.mcp_api_key
    response = client.get("/mcp/tools", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    tool_names = [tool["name"] for tool in response.json()["tools"]]
    assert "write_reservation" in tool_names
