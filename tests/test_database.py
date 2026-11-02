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
