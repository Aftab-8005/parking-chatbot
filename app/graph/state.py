from typing import Optional, TypedDict


class ChatState(TypedDict):
    user_message: str
    intent: str
    reservation_slots: dict
    reservation_in_progress: bool
    response: str
    reservation_complete: bool


def new_state(user_message: str, previous: Optional[dict] = None) -> ChatState:
    previous = previous or {}
    return ChatState(
        user_message=user_message,
        intent="",
        reservation_slots=previous.get("reservation_slots", {}),
        reservation_in_progress=previous.get("reservation_in_progress", False),
        response="",
        reservation_complete=False,
    )
