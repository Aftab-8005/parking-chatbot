from datetime import datetime
from unittest.mock import MagicMock

from app.database import dynamic_service


def _mock_session_returning(row):
    session = MagicMock()
    query = session.query.return_value
    query.order_by.return_value.first.return_value = row
    return session


def test_get_availability_returns_dict_from_row(monkeypatch):
    row = MagicMock(total_spaces=100, available_spaces=42)
    session = _mock_session_returning(row)
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.get_availability()
    assert result == {"total_spaces": 100, "available_spaces": 42}


def test_get_pricing_returns_none_dict_when_no_rows(monkeypatch):
    session = _mock_session_returning(None)
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.get_pricing()
    assert result == {"hourly_price": None, "daily_price": None, "currency": None}


def test_get_working_hours_returns_dict_from_row(monkeypatch):
    row = MagicMock(opening_time="06:00", closing_time="23:00")
    session = _mock_session_returning(row)
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.get_working_hours()
    assert result == {"opening_time": "06:00", "closing_time": "23:00"}


def test_create_reservation_adds_and_commits_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    dynamic_service.create_reservation(
        session_id="sess-1",
        first_name="Jane",
        last_name="Doe",
        car_number="AB-1234",
        start_time=datetime(2026, 11, 5, 9, 0),
        end_time=datetime(2026, 11, 5, 17, 0),
    )

    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_create_admin_request_marks_reservation_pending(monkeypatch):
    session = MagicMock()
    fake_reservation = MagicMock(status="collected")
    session.get.return_value = fake_reservation
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    request_id = dynamic_service.create_admin_request(reservation_id=1)

    assert request_id
    assert fake_reservation.status == "pending_admin_approval"
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_find_conflicting_reservation_returns_overlap(monkeypatch):
    session = MagicMock()
    fake_row = MagicMock(id=5, status="approved", start_time=datetime(2026, 11, 25, 9, 0), end_time=datetime(2026, 11, 25, 11, 0))
    session.query.return_value.filter.return_value.first.return_value = fake_row
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.find_conflicting_reservation(
        "AB1234", datetime(2026, 11, 25, 10, 0), datetime(2026, 11, 25, 12, 0)
    )
    assert result["id"] == 5


def test_find_conflicting_reservation_returns_none_when_no_overlap(monkeypatch):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.find_conflicting_reservation(
        "AB1234", datetime(2026, 11, 25, 10, 0), datetime(2026, 11, 25, 12, 0)
    )
    assert result is None


def test_find_admin_request_by_reference_matches_prefix(monkeypatch):
    session = MagicMock()
    admin_request = MagicMock(
        request_id="f853d9e2-aaaa-bbbb-cccc-dddddddddddd",
        status="pending",
        admin_response="",
        created_at=datetime(2026, 11, 20),
        responded_at=None,
        reservation_id=1,
    )
    reservation = MagicMock(
        session_id="sess-1",
        first_name="Jane",
        last_name="Doe",
        car_number="AB1234",
        start_time=datetime(2026, 11, 25, 10, 0),
        end_time=datetime(2026, 11, 25, 12, 0),
        status="pending_admin_approval",
        facility="airport",
    )
    session.query.return_value.filter.return_value.first.return_value = admin_request
    session.get.return_value = reservation
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.find_admin_request_by_reference("#f853d9e2")
    assert result["request_id"] == "f853d9e2-aaaa-bbbb-cccc-dddddddddddd"
    assert result["status"] == "pending"


def test_find_admin_request_by_reference_returns_none_when_missing(monkeypatch):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    assert dynamic_service.find_admin_request_by_reference("doesnotexist") is None


def test_record_admin_decision_unknown_request_returns_none(monkeypatch):
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    assert dynamic_service.record_admin_decision("missing", "approved") is None


def test_record_admin_decision_approves_and_updates_reservation(monkeypatch):
    session = MagicMock()
    admin_request = MagicMock(status="pending", reservation_id=1)
    reservation = MagicMock(status="pending_admin_approval")
    session.query.return_value.filter_by.return_value.first.return_value = admin_request
    session.get.return_value = reservation
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    outcome = dynamic_service.record_admin_decision("req-1", "approved")

    assert outcome is not None
    record, changed = outcome
    assert changed is True
    assert admin_request.status == "approved"
    assert reservation.status == "approved"


def test_record_admin_decision_keeps_same_reference_after_approval(monkeypatch):
    session = MagicMock()
    admin_request = MagicMock(status="pending", reservation_id=1, request_id="f853d9e2-aaaa-bbbb-cccc-dddddddddddd")
    reservation = MagicMock(status="pending_admin_approval")
    session.query.return_value.filter_by.return_value.first.return_value = admin_request
    session.get.return_value = reservation
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    record, changed = dynamic_service.record_admin_decision("f853d9e2-aaaa-bbbb-cccc-dddddddddddd", "approved")

    assert changed is True
    assert record["request_id"] == "f853d9e2-aaaa-bbbb-cccc-dddddddddddd"


def test_record_admin_decision_keeps_same_reference_after_rejection(monkeypatch):
    session = MagicMock()
    admin_request = MagicMock(status="pending", reservation_id=1, request_id="f853d9e2-aaaa-bbbb-cccc-dddddddddddd")
    reservation = MagicMock(status="pending_admin_approval")
    session.query.return_value.filter_by.return_value.first.return_value = admin_request
    session.get.return_value = reservation
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    record, changed = dynamic_service.record_admin_decision("f853d9e2-aaaa-bbbb-cccc-dddddddddddd", "rejected")

    assert changed is True
    assert record["request_id"] == "f853d9e2-aaaa-bbbb-cccc-dddddddddddd"
