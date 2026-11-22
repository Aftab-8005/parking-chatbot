from datetime import datetime
from unittest.mock import MagicMock

from app.agents.reservation_agent import (
    ReservationSlots,
    apply_extracted,
    apply_slot_value,
    extract_and_merge,
    next_prompt,
    summarize,
)


def test_next_missing_slot_returns_first_name_when_empty():
    slots = ReservationSlots()
    assert slots.next_missing_slot() == "first_name"
    assert next_prompt(slots) is not None


def test_apply_slot_value_rejects_invalid_car_number():
    slots = ReservationSlots(first_name="Jane", last_name="Doe")
    updated, error = apply_slot_value(slots, "car_number", "!!")
    assert error is not None
    assert updated.car_number is None


def test_apply_slot_value_accepts_valid_car_number():
    slots = ReservationSlots(first_name="Jane", last_name="Doe")
    updated, error = apply_slot_value(slots, "car_number", "ab-1234")
    assert error is None
    assert updated.car_number == "AB-1234"


def test_apply_slot_value_rejects_end_time_before_start_time():
    slots = ReservationSlots(
        first_name="Jane",
        last_name="Doe",
        car_number="AB-1234",
    )
    slots, error = apply_slot_value(slots, "start_time", "2026-11-05 09:00")
    assert error is None
    slots, error = apply_slot_value(slots, "end_time", "2026-11-05 08:00")
    assert error is not None
    assert slots.end_time is None


def test_slots_round_trip_to_and_from_dict():
    slots = ReservationSlots(first_name="Jane", last_name="Doe", car_number="AB-1234")
    slots, _ = apply_slot_value(slots, "start_time", "2026-11-05 09:00")
    slots, _ = apply_slot_value(slots, "end_time", "2026-11-05 17:00")
    assert slots.is_complete()

    restored = ReservationSlots.from_dict(slots.to_dict())
    assert restored.is_complete()
    assert "Jane" in summarize(restored)


def test_apply_extracted_fills_only_empty_slots_with_valid_values():
    slots = ReservationSlots(first_name="Jane")
    extracted = {"first_name": "Ignored", "last_name": "Doe", "car_number": "AB1234"}
    updated = apply_extracted(slots, extracted)
    assert updated.first_name == "Jane"
    assert updated.last_name == "Doe"
    assert updated.car_number == "AB1234"


def test_extract_and_merge_falls_back_to_unchanged_slots_when_llm_unavailable():
    slots = ReservationSlots(first_name="Jane")
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("LLM unavailable")

    result = extract_and_merge(slots, "car ABC123", datetime(2026, 11, 22, 9, 0), llm=llm)
    assert result.first_name == "Jane"
    assert result.car_number is None
