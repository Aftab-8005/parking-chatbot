from datetime import datetime
from unittest.mock import MagicMock

from app.graph import orchestrator_graph


def _fake_reservation(reservation_id: int) -> dict:
    return {
        "id": reservation_id,
        "first_name": "Jane",
        "last_name": "Doe",
        "car_number": "AB-1234",
        "start_time": datetime(2026, 11, 5, 9, 0),
        "end_time": datetime(2026, 11, 5, 17, 0),
        "status": "pending_admin_approval",
        "created_at": datetime(2026, 11, 1, 8, 0),
        "decided_at": None,
    }


def _patch_collaborators(monkeypatch, reservation_id: int):
    monkeypatch.setattr(
        orchestrator_graph.dynamic_service, "get_reservation", lambda rid: _fake_reservation(reservation_id)
    )
    update_mock = MagicMock()
    monkeypatch.setattr(orchestrator_graph.dynamic_service, "update_reservation_status", update_mock)
    notify_mock = MagicMock(return_value=False)
    monkeypatch.setattr(orchestrator_graph.admin_agent, "request_approval", notify_mock)
    write_mock = MagicMock(return_value="Jane Doe | AB-1234 | period | time")
    monkeypatch.setattr(orchestrator_graph, "write_confirmed_reservation", write_mock)
    return update_mock, notify_mock, write_mock


def test_start_approval_pipeline_notifies_admin_and_pauses(monkeypatch):
    update_mock, notify_mock, write_mock = _patch_collaborators(monkeypatch, 9001)

    result = orchestrator_graph.start_approval_pipeline(9001)

    assert result["awaiting_admin_decision"] is True
    notify_mock.assert_called_once()
    write_mock.assert_not_called()


def test_resume_with_decision_approved_writes_via_mcp(monkeypatch):
    update_mock, notify_mock, write_mock = _patch_collaborators(monkeypatch, 9002)
    orchestrator_graph.start_approval_pipeline(9002)

    result = orchestrator_graph.resume_with_decision(9002, "approved")

    assert result["final_status"] == "recorded"
    assert result["recorded_line"] == "Jane Doe | AB-1234 | period | time"
    write_mock.assert_called_once()
    # Side effects before interrupt() must not re-run on resume.
    notify_mock.assert_called_once()
    assert update_mock.call_args_list[-1].args == (9002, "recorded")


def test_resume_with_decision_self_heals_when_pipeline_never_started(monkeypatch):
    """Simulates a process restart wiping the in-memory checkpointer: the
    admin posts a decision for a reservation whose pipeline was never
    started (or was lost) in this process. resume_with_decision should
    recover instead of raising InvalidUpdateError."""
    update_mock, notify_mock, write_mock = _patch_collaborators(monkeypatch, 9004)

    result = orchestrator_graph.resume_with_decision(9004, "approved")

    assert result["final_status"] == "recorded"
    notify_mock.assert_called_once()
    write_mock.assert_called_once()


def test_resume_with_decision_rejected_skips_mcp_write(monkeypatch):
    update_mock, notify_mock, write_mock = _patch_collaborators(monkeypatch, 9003)
    orchestrator_graph.start_approval_pipeline(9003)

    result = orchestrator_graph.resume_with_decision(9003, "rejected")

    assert result["final_status"] == "rejected"
    write_mock.assert_not_called()
    assert update_mock.call_args_list[-1].args == (9003, "rejected")
