import pytest

from mcp_server import storage


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    data_dir = tmp_path / "reservations"
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "OUTPUT_FILE", data_dir / "confirmed_reservations.txt")
    monkeypatch.setattr(storage, "LOCK_FILE", data_dir / ".confirmed_reservations.lock")
    return data_dir


def test_write_reservation_appends_formatted_line(isolated_storage):
    line = storage.write_reservation("Jane Doe", "AB-1234", "2026-11-05 09:00 - 17:00", "2026-11-02T10:00:00")
    assert line == "Jane Doe | AB-1234 | 2026-11-05 09:00 - 17:00 | 2026-11-02T10:00:00"
    assert storage.OUTPUT_FILE.read_text(encoding="utf-8") == line + "\n"


def test_write_reservation_sanitizes_delimiter_injection(isolated_storage):
    line = storage.write_reservation("Jane | Fake\nRecord", "AB-1234", "period", "time")
    assert "\n" not in line.split(" | ")[0]
    assert line.count("|") == 3  # exactly the 3 field separators, no injected extra record


def test_write_reservation_rejects_empty_field(isolated_storage):
    with pytest.raises(storage.InvalidReservationFieldError):
        storage.write_reservation("", "AB-1234", "period", "time")


def test_write_reservation_rejects_overlong_field(isolated_storage):
    with pytest.raises(storage.InvalidReservationFieldError):
        storage.write_reservation("x" * 300, "AB-1234", "period", "time")
