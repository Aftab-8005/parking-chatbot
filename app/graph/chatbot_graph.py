"""LangGraph orchestration of the Stage-1 chatbot.

START -> classify_intent -> {handle_reservation | handle_reservation_status |
handle_dynamic_info | handle_static_info} -> guardrail_filter -> END

- classify_intent: routes each turn based on reservation-in-progress state and keywords.
- handle_reservation: interactive slot-filling for a parking reservation (app.agents.reservation_agent).
- handle_reservation_status: lets the user ask whether an admin has approved/rejected a
  reservation (the feedback loop back from Stage 2/4 into this chatbot).
- handle_dynamic_info: looks up availability / prices / working hours from PostgreSQL (app.database.dynamic_service).
- handle_static_info: RAG over the Qdrant knowledge base (app.rag.chain).
- guardrail_filter: redacts any PII that may have leaked into the final response before it reaches the user.
"""

from __future__ import annotations

import logging
import re

from langgraph.graph import END, START, StateGraph

from app.agents.reservation_agent import (
    ReservationSlots,
    apply_slot_value,
    next_prompt,
    summarize,
)
from app.database import dynamic_service
from app.graph.state import ChatState
from app.rag.chain import answer_static_question
from app.security.guardrails import redact_pii

_RESERVATION_KEYWORDS = ("reserve", "reservation", "book", "booking")
_AVAILABILITY_KEYWORDS = ("available", "availability", "free space", "spaces left", "how many spaces")
_PRICE_KEYWORDS = ("price", "cost", "fee", "how much")
_HOURS_KEYWORDS = ("working hours", "opening", "closing", "open", "close", "hours")
_STATUS_KEYWORDS = (
    "status",
    "approved",
    "rejected",
    "confirmed",
    "decision",
    "update on my",
    "has my reservation",
    "been approved",
    "been rejected",
)

_RESERVATION_ID_RE = re.compile(r"#\s*(\d+)|\breservation\s*(?:number\s*)?(\d+)\b", re.IGNORECASE)

logger = logging.getLogger("parking_chatbot.graph")


def classify_intent(state: ChatState) -> ChatState:
    message = state["user_message"].lower()

    if state.get("reservation_in_progress"):
        state["intent"] = "reservation"
        return state

    if any(keyword in message for keyword in _STATUS_KEYWORDS):
        state["intent"] = "reservation_status"
    elif any(keyword in message for keyword in _RESERVATION_KEYWORDS):
        state["intent"] = "reservation"
    elif any(keyword in message for keyword in _AVAILABILITY_KEYWORDS + _PRICE_KEYWORDS + _HOURS_KEYWORDS):
        state["intent"] = "dynamic_info"
    else:
        state["intent"] = "static_info"
    return state


def route_after_classify(state: ChatState) -> str:
    return state["intent"]


def handle_reservation(state: ChatState) -> ChatState:
    slots = ReservationSlots.from_dict(state.get("reservation_slots"))
    message = state["user_message"]

    if not state.get("reservation_in_progress"):
        state["reservation_in_progress"] = True
        state["response"] = next_prompt(slots) or ""
        state["reservation_slots"] = slots.to_dict()
        return state

    missing_slot = slots.next_missing_slot()
    if missing_slot is None:
        state["response"] = summarize(slots)
        state["reservation_slots"] = slots.to_dict()
        return state

    slots, error = apply_slot_value(slots, missing_slot, message)
    if error:
        state["response"] = error
        state["reservation_slots"] = slots.to_dict()
        return state

    if slots.is_complete():
        reservation_id = dynamic_service.create_reservation(
            first_name=slots.first_name,
            last_name=slots.last_name,
            car_number=slots.car_number,
            start_time=slots.start_time,
            end_time=slots.end_time,
            status="pending_admin_approval",
        )
        state["response"] = summarize(slots) + f" (Reservation reference: #{reservation_id})"
        state["reservation_in_progress"] = False
        state["reservation_complete"] = True
        state["reservation_id"] = reservation_id
        state["last_reservation_id"] = reservation_id
    else:
        state["response"] = next_prompt(slots) or ""

    state["reservation_slots"] = slots.to_dict()
    return state


_STATUS_MESSAGES = {
    "pending_admin_approval": "is still awaiting administrator approval.",
    "approved": "has been approved by the administrator.",
    "recorded": "has been approved and confirmed -- you're all set!",
    "rejected": "was rejected by the administrator.",
}


def handle_reservation_status(state: ChatState) -> ChatState:
    """Let the user ask the chatbot whether the administrator has
    approved/rejected a reservation it already collected (Stage 2/4
    feedback loop back to the user-facing chatbot)."""
    message = state["user_message"]
    match = _RESERVATION_ID_RE.search(message)
    reservation_id = int(match.group(1) or match.group(2)) if match else state.get("last_reservation_id")

    if reservation_id is None:
        state["response"] = (
            "Which reservation would you like me to check? Please give me the reference number "
            "(e.g. #3), or make a new reservation first."
        )
        return state

    reservation = dynamic_service.get_reservation(reservation_id)
    if reservation is None:
        state["response"] = f"I couldn't find a reservation with reference #{reservation_id}."
        return state

    status_text = _STATUS_MESSAGES.get(reservation["status"], f"has status '{reservation['status']}'.")
    state["response"] = f"Reservation #{reservation_id} {status_text}"
    return state


def handle_dynamic_info(state: ChatState) -> ChatState:
    message = state["user_message"].lower()
    parts = []

    if any(k in message for k in _AVAILABILITY_KEYWORDS):
        availability = dynamic_service.get_availability()
        parts.append(
            f"There are {availability['available_spaces']} of {availability['total_spaces']} "
            "parking spaces currently available."
        )
    if any(k in message for k in _PRICE_KEYWORDS):
        pricing = dynamic_service.get_pricing()
        parts.append(
            f"Parking costs {pricing['hourly_price']} {pricing['currency']}/hour "
            f"or {pricing['daily_price']} {pricing['currency']}/day."
        )
    if any(k in message for k in _HOURS_KEYWORDS):
        hours = dynamic_service.get_working_hours()
        parts.append(f"We are open from {hours['opening_time']} to {hours['closing_time']} every day.")

    if not parts:
        availability = dynamic_service.get_availability()
        pricing = dynamic_service.get_pricing()
        hours = dynamic_service.get_working_hours()
        parts.append(
            f"Currently {availability['available_spaces']}/{availability['total_spaces']} spaces are free, "
            f"open {hours['opening_time']}-{hours['closing_time']}, "
            f"pricing is {pricing['hourly_price']} {pricing['currency']}/hour."
        )

    state["response"] = " ".join(parts)
    return state


def handle_static_info(state: ChatState) -> ChatState:
    try:
        state["response"] = answer_static_question(state["user_message"])
    except Exception:
        logger.exception("Static-info lookup failed (RAG/LLM/vector store unavailable).")
        state["response"] = (
            "Sorry, I can't look that up right now. You can ask about working hours, prices, "
            "availability, or make a reservation."
        )
    return state


def guardrail_filter(state: ChatState) -> ChatState:
    # The reservation flow intentionally echoes back the name the user just
    # typed in (e.g. "Thanks Jane Doe, ..."); don't let NER-based redaction
    # censor that. Other intents still get full PII redaction since any name
    # appearing there would come from the knowledge base/dynamic data, not
    # from something the user just said.
    redact_names = state["intent"] not in ("reservation", "reservation_status")
    state["response"] = redact_pii(state["response"], redact_names=redact_names)
    return state


def build_graph():
    graph = StateGraph(ChatState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_reservation", handle_reservation)
    graph.add_node("handle_reservation_status", handle_reservation_status)
    graph.add_node("handle_dynamic_info", handle_dynamic_info)
    graph.add_node("handle_static_info", handle_static_info)
    graph.add_node("guardrail_filter", guardrail_filter)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "reservation": "handle_reservation",
            "reservation_status": "handle_reservation_status",
            "dynamic_info": "handle_dynamic_info",
            "static_info": "handle_static_info",
        },
    )
    graph.add_edge("handle_reservation", "guardrail_filter")
    graph.add_edge("handle_reservation_status", "guardrail_filter")
    graph.add_edge("handle_dynamic_info", "guardrail_filter")
    graph.add_edge("handle_static_info", "guardrail_filter")
    graph.add_edge("guardrail_filter", END)

    return graph.compile()


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
