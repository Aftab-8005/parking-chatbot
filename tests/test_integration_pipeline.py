"""End-to-end test of the full pipeline across all four stages:

  Stage 1: the RAG chatbot collects a reservation through multi-turn chat.
  Stage 2: the admin agent is notified and the reservation awaits a decision.
  Stage 3: on approval, the (in-process) MCP server writes the confirmed
           reservation to a file.
  Stage 4: the LangGraph orchestrator ties the escalation + approval + file
           write together via interrupt()/Command, driven entirely through
           the public REST API (/chat and /admin/...).

External services (OpenAI, SMTP, the MCP server's HTTP transport) are
replaced with lightweight fakes so this test runs offline and deterministically;
everything else (the DB, the reservation slot-filling, the orchestrator graph,
the MCP file-writing/validation logic) is exercised for real.
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import admin_agent
from app.database import dynamic_service
from app.database.models import Base
from app.graph import orchestrator_graph
from app.main import app
from mcp_server import storage as mcp_storage


def test_full_reservation_approval_pipeline_end_to_end(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session_local())

    notify_mock = MagicMock(return_value=False)
    monkeypatch.setattr(admin_agent, "request_approval", notify_mock)

    data_dir = tmp_path / "reservations"
    monkeypatch.setattr(mcp_storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(mcp_storage, "OUTPUT_FILE", data_dir / "confirmed_reservations.txt")
    monkeypatch.setattr(mcp_storage, "LOCK_FILE", data_dir / ".confirmed_reservations.lock")
    monkeypatch.setattr(
        orchestrator_graph,
        "write_confirmed_reservation",
        lambda name, car_number, period, approval_time: mcp_storage.write_reservation(
            name, car_number, period, approval_time
        ),
    )

    client = TestClient(app)
    session_id = "integration-session"

    conversation = [
        "I'd like to book a parking space",
        "Jane",
        "Doe",
        "AB-1234",
        "2026-11-05 09:00",
        "2026-11-05 17:00",
    ]
    last_response = None
    for message in conversation:
        response = client.post("/chat", json={"session_id": session_id, "message": message})
        assert response.status_code == 200
        last_response = response.json()

    assert "Reservation reference" in last_response["response"]
    reservation_id = int(last_response["response"].rsplit("#", 1)[-1].rstrip(")"))
    notify_mock.assert_called_once()

    pending = client.get("/admin/reservations/pending").json()
    assert any(r["id"] == reservation_id for r in pending)

    decision_response = client.post(
        f"/admin/reservations/{reservation_id}/decision", json={"decision": "approved"}
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["final_status"] == "recorded"

    written = (data_dir / "confirmed_reservations.txt").read_text(encoding="utf-8")
    assert "Jane Doe" in written
    assert "AB-1234" in written

    no_longer_pending = client.get("/admin/reservations/pending").json()
    assert not any(r["id"] == reservation_id for r in no_longer_pending)


def test_full_reservation_rejection_pipeline_end_to_end(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session_local())
    monkeypatch.setattr(admin_agent, "request_approval", MagicMock(return_value=False))

    write_mock = MagicMock()
    monkeypatch.setattr(orchestrator_graph, "write_confirmed_reservation", write_mock)

    client = TestClient(app)
    session_id = "integration-session-reject"

    conversation = [
        "book a reservation",
        "John",
        "Smith",
        "XY-9876",
        "2026-12-01 10:00",
        "2026-12-01 18:00",
    ]
    last_response = None
    for message in conversation:
        response = client.post("/chat", json={"session_id": session_id, "message": message})
        last_response = response.json()

    reservation_id = int(last_response["response"].rsplit("#", 1)[-1].rstrip(")"))

    decision_response = client.post(
        f"/admin/reservations/{reservation_id}/decision", json={"decision": "rejected"}
    )

    assert decision_response.status_code == 200
    assert decision_response.json()["final_status"] == "rejected"
    write_mock.assert_not_called()
