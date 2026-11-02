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
        first_name="Jane",
        last_name="Doe",
        car_number="AB-1234",
        start_time=datetime(2026, 11, 5, 9, 0),
        end_time=datetime(2026, 11, 5, 17, 0),
    )

    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_get_reservation_returns_none_when_missing(monkeypatch):
    session = MagicMock()
    session.get.return_value = None
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    assert dynamic_service.get_reservation(123) is None


def test_get_reservation_returns_dict_from_row(monkeypatch):
    row = MagicMock(
        id=5,
        first_name="Jane",
        last_name="Doe",
        car_number="AB-1234",
        start_time=datetime(2026, 11, 5, 9, 0),
        end_time=datetime(2026, 11, 5, 17, 0),
        status="pending_admin_approval",
        created_at=datetime(2026, 11, 1, 8, 0),
        decided_at=None,
    )
    session = MagicMock()
    session.get.return_value = row
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.get_reservation(5)
    assert result["id"] == 5
    assert result["status"] == "pending_admin_approval"


def test_list_pending_reservations_filters_by_status(monkeypatch):
    row = MagicMock(
        id=5,
        first_name="Jane",
        last_name="Doe",
        car_number="AB-1234",
        start_time=datetime(2026, 11, 5, 9, 0),
        end_time=datetime(2026, 11, 5, 17, 0),
        status="pending_admin_approval",
        created_at=datetime(2026, 11, 1, 8, 0),
        decided_at=None,
    )
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    result = dynamic_service.list_pending_reservations()
    assert len(result) == 1
    assert result[0]["status"] == "pending_admin_approval"


def test_update_reservation_status_commits_new_status(monkeypatch):
    row = MagicMock(status="pending_admin_approval", decided_at=None)
    session = MagicMock()
    session.get.return_value = row
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    decided_at = datetime(2026, 11, 2, 10, 0)
    result = dynamic_service.update_reservation_status(5, "approved", decided_at=decided_at)

    assert row.status == "approved"
    assert row.decided_at == decided_at
    session.commit.assert_called_once()
    assert result["status"] == "approved"


def test_update_reservation_status_returns_none_when_missing(monkeypatch):
    session = MagicMock()
    session.get.return_value = None
    monkeypatch.setattr(dynamic_service, "get_session", lambda: session)

    assert dynamic_service.update_reservation_status(999, "approved") is None
