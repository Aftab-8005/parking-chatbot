from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.api.routes as routes_module
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_returns_response(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {
        "response": "Hello!",
        "intent": "static_info",
        "reservation_slots": {},
        "reservation_in_progress": False,
    }
    monkeypatch.setattr(routes_module, "get_compiled_graph", lambda: fake_graph)

    response = client.post("/chat", json={"session_id": "abc", "message": "hi"})
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Hello!"
    assert body["intent"] == "static_info"


def test_chat_endpoint_persists_session_state(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {
        "response": "What is your first name?",
        "intent": "reservation",
        "reservation_slots": {"first_name": None},
        "reservation_in_progress": True,
    }
    monkeypatch.setattr(routes_module, "get_compiled_graph", lambda: fake_graph)

    client.post("/chat", json={"session_id": "session-2", "message": "book"})
    assert routes_module._sessions["session-2"]["reservation_in_progress"] is True
