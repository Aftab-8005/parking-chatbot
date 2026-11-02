from fastapi.testclient import TestClient

import app.api.admin_routes as admin_routes_module
from app.main import app

client = TestClient(app)

_PENDING = {
    "id": 7,
    "first_name": "Jane",
    "last_name": "Doe",
    "car_number": "AB-1234",
    "start_time": "2026-11-05 09:00:00",
    "end_time": "2026-11-05 17:00:00",
    "status": "pending_admin_approval",
    "created_at": "2026-11-01 08:00:00",
    "decided_at": None,
}


def test_admin_page_renders_html():
    response = client.get("/admin")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Approve" in response.text


def test_list_pending_returns_reservations(monkeypatch):
    monkeypatch.setattr(admin_routes_module.dynamic_service, "list_pending_reservations", lambda: [_PENDING])

    response = client.get("/admin/reservations/pending")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == 7
    assert body[0]["status"] == "pending_admin_approval"


def test_decide_returns_404_for_unknown_reservation(monkeypatch):
    monkeypatch.setattr(admin_routes_module.dynamic_service, "get_reservation", lambda rid: None)

    response = client.post("/admin/reservations/999/decision", json={"decision": "approved"})

    assert response.status_code == 404


def test_decide_returns_409_when_not_awaiting_approval(monkeypatch):
    already_decided = dict(_PENDING, status="approved")
    monkeypatch.setattr(admin_routes_module.dynamic_service, "get_reservation", lambda rid: already_decided)

    response = client.post("/admin/reservations/7/decision", json={"decision": "approved"})

    assert response.status_code == 409


def test_decide_updates_status_and_returns_result(monkeypatch):
    monkeypatch.setattr(admin_routes_module.dynamic_service, "get_reservation", lambda rid: _PENDING)
    update_calls = []
    monkeypatch.setattr(
        admin_routes_module.dynamic_service,
        "update_reservation_status",
        lambda rid, status, decided_at=None: update_calls.append((rid, status)),
    )

    response = client.post("/admin/reservations/7/decision", json={"decision": "approved"})

    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "approved"
    assert update_calls == [(7, "approved")]


def test_decide_rejects_invalid_decision_value(monkeypatch):
    monkeypatch.setattr(admin_routes_module.dynamic_service, "get_reservation", lambda rid: _PENDING)

    response = client.post("/admin/reservations/7/decision", json={"decision": "maybe"})

    assert response.status_code == 422
