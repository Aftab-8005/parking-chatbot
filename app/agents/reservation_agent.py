"""Interactive slot-filling for a parking reservation request.

The chatbot graph drives this agent one user turn at a time: on each turn it
feeds the user's latest message as the value for whichever slot is currently
missing, validates it, and asks for the next missing slot until all required
fields (first name, surname, car number, start time, end time) are collected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from dateutil import parser as date_parser

SLOT_ORDER = ["first_name", "last_name", "car_number", "start_time", "end_time"]

SLOT_PROMPTS = {
    "first_name": "Sure, I can help you reserve a parking space. What is your first name?",
    "last_name": "What is your surname?",
    "car_number": "What is your car's license plate number?",
    "start_time": "When would you like the reservation to start? (e.g. 2026-11-05 09:00)",
    "end_time": "When would you like the reservation to end? (e.g. 2026-11-05 17:00)",
}

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{0,49}$")
_CAR_NUMBER_RE = re.compile(r"^[A-Za-z0-9\-]{2,12}$")


@dataclass
class ReservationSlots:
    first_name: str | None = None
    last_name: str | None = None
    car_number: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "ReservationSlots":
        if not data:
            return cls()
        start = data.get("start_time")
        end = data.get("end_time")
        return cls(
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            car_number=data.get("car_number"),
            start_time=datetime.fromisoformat(start) if start else None,
            end_time=datetime.fromisoformat(end) if end else None,
        )

    def to_dict(self) -> dict:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "car_number": self.car_number,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    def next_missing_slot(self) -> str | None:
        for slot in SLOT_ORDER:
            if getattr(self, slot) is None:
                return slot
        return None

    def is_complete(self) -> bool:
        return self.next_missing_slot() is None


def validate_name(value: str) -> tuple[bool, str | None, str | None]:
    value = value.strip()
    if _NAME_RE.match(value):
        return True, value, None
    return False, None, "That doesn't look like a valid name. Please use letters only."


def validate_car_number(value: str) -> tuple[bool, str | None, str | None]:
    value = value.strip().upper()
    if _CAR_NUMBER_RE.match(value):
        return True, value, None
    return False, None, "Please provide a valid car number (letters/digits/dashes, 2-12 characters)."


def validate_datetime(value: str) -> tuple[bool, datetime | None, str | None]:
    try:
        parsed = date_parser.parse(value.strip())
        return True, parsed, None
    except (ValueError, OverflowError):
        return False, None, "I couldn't understand that date/time. Please use a format like 2026-11-05 09:00."


_VALIDATORS = {
    "first_name": validate_name,
    "last_name": validate_name,
    "car_number": validate_car_number,
    "start_time": validate_datetime,
    "end_time": validate_datetime,
}


def apply_slot_value(
    slots: ReservationSlots, slot_name: str, raw_value: str
) -> tuple[ReservationSlots, str | None]:
    """Validate and apply `raw_value` to `slot_name`.

    Returns (updated_slots, error_message). error_message is None on success.
    """
    valid, parsed, error = _VALIDATORS[slot_name](raw_value)
    if not valid:
        return slots, error

    if slot_name == "end_time" and slots.start_time is not None and parsed <= slots.start_time:
        return slots, "The reservation end time must be after the start time. When should it end?"

    setattr(slots, slot_name, parsed)
    return slots, None


def next_prompt(slots: ReservationSlots) -> str | None:
    missing = slots.next_missing_slot()
    if missing is None:
        return None
    return SLOT_PROMPTS[missing]


def summarize(slots: ReservationSlots) -> str:
    return (
        f"Thanks {slots.first_name} {slots.last_name}. I've collected your reservation request "
        f"for car {slots.car_number} from {slots.start_time} to {slots.end_time}. "
        "It has been submitted for administrator approval."
    )
