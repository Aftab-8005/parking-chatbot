import pytest

from app.mcp import server as mcp_server


@pytest.fixture(autouse=True)
def _isolated_reservations_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server.settings, "reservations_file_path", "data/reservations/test_output.txt")
    path = mcp_server._resolve_reservations_path()
    yield path
    if path.exists():
        path.unlink()


def test_save_confirmed_reservation_valid_input_writes_line():
    result = mcp_server.save_confirmed_reservation(
        token=mcp_server.settings.mcp_auth_token,
        request_id="req-12345678",
        name="Jane Doe",
        car_number="AB1234",
        period_start="2026-11-25T10:00:00",
        period_end="2026-11-25T12:00:00",
        approval_time="2026-11-22T18:30:00",
    )
    assert result["stored"] is True
    assert "Jane Doe | AB1234 |" in result["line"]


def test_save_confirmed_reservation_rejects_invalid_token():
    with pytest.raises(mcp_server.ReservationValidationError):
        mcp_server.save_confirmed_reservation(
            token="wrong-token",
            request_id="req-12345678",
            name="Jane Doe",
            car_number="AB1234",
            period_start="2026-11-25T10:00:00",
            period_end="2026-11-25T12:00:00",
            approval_time="2026-11-22T18:30:00",
        )


def test_save_confirmed_reservation_rejects_invalid_car_number():
    with pytest.raises(mcp_server.ReservationValidationError):
        mcp_server.save_confirmed_reservation(
            token=mcp_server.settings.mcp_auth_token,
            request_id="req-12345678",
            name="Jane Doe",
            car_number="!!!invalid!!!",
            period_start="2026-11-25T10:00:00",
            period_end="2026-11-25T12:00:00",
            approval_time="2026-11-22T18:30:00",
        )


def test_save_confirmed_reservation_rejects_end_before_start():
    with pytest.raises(mcp_server.ReservationValidationError):
        mcp_server.save_confirmed_reservation(
            token=mcp_server.settings.mcp_auth_token,
            request_id="req-12345678",
            name="Jane Doe",
            car_number="AB1234",
            period_start="2026-11-25T12:00:00",
            period_end="2026-11-25T10:00:00",
            approval_time="2026-11-22T18:30:00",
        )


def test_resolve_reservations_path_rejects_escape_outside_data_dir(monkeypatch):
    monkeypatch.setattr(mcp_server.settings, "reservations_file_path", "../../outside.txt")
    with pytest.raises(mcp_server.ReservationValidationError):
        mcp_server._resolve_reservations_path()
