"""LangGraph orchestration of the parking chatbot (Stages 1, 2 & 4).

START -> classify_intent -> {
    reservation    -> handle_reservation -> [submit_to_admin -> await_admin_decision (interrupt) ->
                                              {store_via_mcp | reject_notify}]
    dynamic_info   -> handle_dynamic_info
    static_info    -> handle_static_info
    awaiting_admin -> handle_awaiting_admin
} -> guardrail_filter -> END

Human-in-the-loop: `await_admin_decision` calls LangGraph's `interrupt()`, which
genuinely pauses the run (the graph is checkpointed to SQLite via
`app.graph.checkpointer`). The administrator API resumes the same thread later
with `Command(resume=...)`, which is what lets the reservation survive across
HTTP requests -- and even an app restart -- while awaiting a human decision.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.reservation_agent import (
    ReservationSlots,
    apply_slot_value,
    extract_and_merge,
    next_prompt,
    summarize,
)
from app.database import dynamic_service, facilities
from app.graph.checkpointer import get_checkpointer
from app.graph.state import ChatState
from app.mcp.client import McpUnavailableError, save_confirmed_reservation
from app.rag.chain import answer_static_question
from app.security.guardrails import redact_pii

_RESERVATION_KEYWORDS = ("reserve", "reservation", "book", "booking")
_AVAILABILITY_KEYWORDS = ("available", "availability", "free space", "spaces left", "how many spaces")
_PRICE_KEYWORDS = ("price", "pricing", "rate", "rates", "cost", "fee", "how much")
_HOURS_KEYWORDS = ("working hours", "opening", "closing", "open", "close", "hours")
_STATUS_KEYWORDS = ("status", "approved", "approve", "rejected", "reject", "pending")

_HASH_REFERENCE_RE = re.compile(r"#\s*([0-9a-zA-Z_-]{3,40})")
_BARE_REFERENCE_RE = re.compile(r"(?<![\w#])([0-9a-fA-F]{8})(?![\w])")

logger = logging.getLogger("parking_chatbot.graph")


def extract_reference_number(message: str) -> str | None:
    """Pull a reservation reference number out of a free-text message.
    Supports both `#f853d9e2` and bare `f853d9e2` forms."""
    match = _HASH_REFERENCE_RE.search(message)
    if match:
        return match.group(1)[:8].lower()
    match = _BARE_REFERENCE_RE.search(message)
    if match:
        return match.group(1).lower()
    return None


def classify_intent(state: ChatState) -> ChatState:
    raw_message = state["user_message"]
    message = raw_message.lower()

    if state.get("reservation_status") == "pending_admin_approval" and state.get("request_id"):
        state["intent"] = "awaiting_admin"
        return state

    if state.get("reservation_in_progress"):
        state["intent"] = "reservation"
        return state

    explicit_reference = bool(_HASH_REFERENCE_RE.search(raw_message))
    reference = extract_reference_number(raw_message)
    mentions_status = any(keyword in message for keyword in _STATUS_KEYWORDS)
    mentions_reservation_ref = "reservation" in message or "reference" in message

    if explicit_reference or (reference and mentions_status) or (mentions_status and mentions_reservation_ref):
        state["intent"] = "reservation_status"
        return state

    if any(keyword in message for keyword in _RESERVATION_KEYWORDS):
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
    was_in_progress = state.get("reservation_in_progress", False)

    # An explicit "I want to (make) a(nother) reservation/booking" while a
    # previous attempt is still (or stuck) in progress means the user wants
    # to start over, not supply a value for the currently-missing slot (e.g.
    # a name or date never contains these words). Without this, a prior
    # terminal failure that didn't fully clear the in-progress flag -- or a
    # user abandoning a stalled attempt mid-correction -- would make the next
    # free-form "new reservation" message get swallowed as a bogus slot
    # answer instead of restarting the flow.
    if was_in_progress and any(keyword in message.lower() for keyword in _RESERVATION_KEYWORDS):
        slots = ReservationSlots()
        was_in_progress = False

    if slots.facility is None:
        matched_facility = facilities.match_facility(message)
        if matched_facility:
            slots.facility = matched_facility

    if not was_in_progress:
        state["reservation_in_progress"] = True
        state["response"] = next_prompt(slots) or ""
        state["reservation_slots"] = slots.to_dict()
        return state

    # Best-effort: let the user fill multiple slots in one free-form message
    # (e.g. "book for Jane Doe, car ABC123, tomorrow 9am to 5pm"). Falls back
    # to leaving `slots` unchanged if the LLM is unavailable.
    before = slots.to_dict()
    slots = extract_and_merge(slots, message, datetime.utcnow())
    extracted_anything = slots.to_dict() != before

    missing_slot = slots.next_missing_slot()
    if missing_slot is not None and not extracted_anything:
        slots, error = apply_slot_value(slots, missing_slot, message)
        if error:
            state["response"] = error
            state["reservation_slots"] = slots.to_dict()
            return state
        missing_slot = slots.next_missing_slot()
    elif missing_slot is not None:
        state["response"] = next_prompt(slots) or ""
        state["reservation_slots"] = slots.to_dict()
        return state

    if slots.is_complete():
        state["reservation_in_progress"] = False
        state["reservation_complete"] = True
    else:
        state["response"] = next_prompt(slots) or ""

    state["reservation_slots"] = slots.to_dict()
    return state


def route_after_reservation(state: ChatState) -> str:
    return "submit" if state.get("reservation_complete") else "continue"


def submit_to_admin(state: ChatState, config) -> ChatState:
    """Create the reservation + admin-request records and hand off to the
    administrator. No `interrupt()` here -- side effects in this node must
    stay out of `await_admin_decision`, since LangGraph re-runs a node's body
    from the top when the run resumes past an interrupt() inside it."""
    session_id = config["configurable"]["thread_id"]
    slots = ReservationSlots.from_dict(state.get("reservation_slots"))

    conflict = dynamic_service.find_conflicting_reservation(slots.car_number, slots.start_time, slots.end_time)
    if conflict is not None:
        # Terminal failure for this attempt: clear every transient
        # slot-filling field (not just the slots) so the next message is
        # free to start a brand-new reservation instead of being treated as
        # a continuation of this abandoned one.
        state["reservation_status"] = None
        state["reservation_complete"] = False
        state["reservation_in_progress"] = False
        state["reservation_slots"] = {}
        state["response"] = (
            f"Car {slots.car_number} already has a reservation ({conflict['status']}) from "
            f"{conflict['start_time']} to {conflict['end_time']} that overlaps this request. "
            "Please choose a different time, or wait for that request to be resolved."
        )
        return state

    reservation_id = dynamic_service.create_reservation(
        session_id=session_id,
        first_name=slots.first_name,
        last_name=slots.last_name,
        car_number=slots.car_number,
        start_time=slots.start_time,
        end_time=slots.end_time,
        status="collected",
        facility=slots.facility or facilities.DEFAULT_FACILITY,
    )
    request_id = dynamic_service.create_admin_request(reservation_id)

    state["reservation_id"] = reservation_id
    state["request_id"] = request_id
    state["reservation_status"] = "pending_admin_approval"
    state["response"] = (
        f"{summarize(slots)} Your reference number is #{request_id[:8]}. "
        "I'll let you know as soon as the administrator reviews it."
    )
    logger.info("Reservation %s submitted for admin approval as request %s", reservation_id, request_id)
    return state


def route_after_submit(state: ChatState) -> str:
    return "await_decision" if state.get("request_id") else "skip"


def await_admin_decision(state: ChatState) -> ChatState:
    decision = interrupt(
        {
            "request_id": state.get("request_id"),
            "reservation_id": state.get("reservation_id"),
        }
    )
    state["reservation_status"] = decision.get("decision", "rejected")
    return state


def route_after_admin_decision(state: ChatState) -> str:
    return "approved" if state.get("reservation_status") == "approved" else "rejected"


def _attempt_mcp_storage(reservation_id: int, request_id: str) -> tuple[str, str]:
    """Call the MCP tool for an approved reservation. Returns (status, message).

    Shared by the graph's `store_via_mcp` node and the admin API's manual
    retry endpoint, so "it will be retried" (Stage 3 fallback) is backed by
    one real code path instead of two copies that could drift apart.
    """
    reservation = dynamic_service.get_reservation(reservation_id)
    try:
        save_confirmed_reservation(
            request_id=request_id,
            name=f"{reservation.first_name} {reservation.last_name}",
            car_number=reservation.car_number,
            period_start=reservation.start_time,
            period_end=reservation.end_time,
            approval_time=datetime.utcnow(),
            facility=facilities.facility_name(reservation.facility) or "",
        )
        dynamic_service.mark_reservation_stored(reservation_id)
        return "stored", (
            f"Great news! Your reservation (reference #{request_id[:8]}) has been approved "
            "and confirmed by the administrator."
        )
    except McpUnavailableError:
        logger.exception("MCP server unavailable while storing request %s", request_id)
        dynamic_service.mark_reservation_pending_storage(reservation_id)
        return "approved_pending_storage", (
            f"Your reservation (reference #{request_id[:8]}) was approved by the administrator, "
            "but we couldn't finalize storage right now. It has been safely recorded and will be "
            "retried automatically -- no action needed on your side."
        )


def store_via_mcp(state: ChatState) -> ChatState:
    status, message = _attempt_mcp_storage(state["reservation_id"], state["request_id"])
    state["reservation_status"] = status
    state["response"] = message
    return state


def retry_mcp_storage(request_id: str) -> tuple[str, str]:
    """Manually retry MCP storage for a request stuck in
    `approved_pending_storage` (e.g. after the MCP server was down and has
    since come back up). Used by `POST /admin/requests/{id}/retry-storage`."""
    record = dynamic_service.get_admin_request(request_id)
    if record is None:
        raise ValueError(f"Unknown request id: {request_id}")
    return _attempt_mcp_storage(record["reservation_id"], request_id)


def reject_notify(state: ChatState) -> ChatState:
    request_id = state["request_id"]
    state["response"] = (
        f"Your reservation request (reference #{request_id[:8]}) was not approved by the administrator."
    )
    return state


def handle_awaiting_admin(state: ChatState) -> ChatState:
    request_id = state.get("request_id") or ""
    state["response"] = (
        f"Your reservation request (reference #{request_id[:8]}) is still pending administrator "
        "approval. Please check back shortly."
    )
    return state


def handle_reservation_status(state: ChatState) -> ChatState:
    """Answer "is reference #xxxxxxxx approved?" style questions by looking up
    the actual reservation/admin-request status in the database -- never
    guessed by the LLM."""
    reference = extract_reference_number(state["user_message"])
    if not reference:
        state["response"] = (
            "Please share your reservation reference number (e.g. #f853d9e2) so I can check its status."
        )
        return state

    record = dynamic_service.find_admin_request_by_reference(reference)
    if record is None:
        state["response"] = (
            f"I couldn't find a reservation with reference number #{reference}. "
            "Please check the reference number."
        )
        return state

    ref_display = record["request_id"][:8]
    admin_status = record["status"]
    reservation_status = record["reservation_status"]

    if admin_status == "pending":
        state["response"] = f"Reservation #{ref_display} is currently pending administrator approval."
    elif admin_status == "rejected":
        state["response"] = f"Reservation #{ref_display} has been rejected."
    elif reservation_status == "approved_pending_storage":
        state["response"] = (
            f"Reservation #{ref_display} has been approved, but confirmation storage is still pending."
        )
    elif admin_status == "approved":
        state["response"] = f"Reservation #{ref_display} has been approved."
    else:
        state["response"] = f"Reservation #{ref_display} is currently {reservation_status or admin_status}."

    return state


def handle_dynamic_info(state: ChatState) -> ChatState:
    message = state["user_message"].lower()
    facility_key = facilities.match_facility(message)

    if facility_key is None and ("facility" in message or "facilities" in message):
        names = ", ".join(f["name"] for f in facilities.FACILITIES.values())
        state["response"] = f"We support the following parking facilities: {names}."
        return state

    name = facilities.facility_name(facility_key)
    parts = []

    if any(k in message for k in _AVAILABILITY_KEYWORDS):
        availability = dynamic_service.get_availability(facility_key) if facility_key else dynamic_service.get_availability()
        prefix = f"{name}: " if name else ""
        parts.append(
            f"{prefix}There are {availability['available_spaces']} of {availability['total_spaces']} "
            "parking spaces currently available."
        )
    if any(k in message for k in _PRICE_KEYWORDS):
        pricing = dynamic_service.get_pricing(facility_key) if facility_key else dynamic_service.get_pricing()
        prefix = f"{name}: " if name else ""
        parts.append(
            f"{prefix}Parking costs {pricing['hourly_price']} {pricing['currency']}/hour "
            f"or {pricing['daily_price']} {pricing['currency']}/day."
        )
    if any(k in message for k in _HOURS_KEYWORDS):
        hours = dynamic_service.get_working_hours(facility_key) if facility_key else dynamic_service.get_working_hours()
        prefix = f"{name} is" if name else "We are"
        parts.append(f"{prefix} open from {hours['opening_time']} to {hours['closing_time']} every day.")

    if not parts:
        availability = dynamic_service.get_availability(facility_key) if facility_key else dynamic_service.get_availability()
        pricing = dynamic_service.get_pricing(facility_key) if facility_key else dynamic_service.get_pricing()
        hours = dynamic_service.get_working_hours(facility_key) if facility_key else dynamic_service.get_working_hours()
        prefix = f"{name}: " if name else ""
        parts.append(
            f"{prefix}Currently {availability['available_spaces']}/{availability['total_spaces']} spaces are free, "
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
    redact_names = state["intent"] != "reservation"
    state["response"] = redact_pii(state["response"], redact_names=redact_names)
    return state


def build_graph():
    graph = StateGraph(ChatState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_reservation", handle_reservation)
    graph.add_node("submit_to_admin", submit_to_admin)
    graph.add_node("await_admin_decision", await_admin_decision)
    graph.add_node("store_via_mcp", store_via_mcp)
    graph.add_node("reject_notify", reject_notify)
    graph.add_node("handle_awaiting_admin", handle_awaiting_admin)
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
            "dynamic_info": "handle_dynamic_info",
            "static_info": "handle_static_info",
            "awaiting_admin": "handle_awaiting_admin",
            "reservation_status": "handle_reservation_status",
        },
    )
    graph.add_conditional_edges(
        "handle_reservation",
        route_after_reservation,
        {"submit": "submit_to_admin", "continue": "guardrail_filter"},
    )
    graph.add_conditional_edges(
        "submit_to_admin",
        route_after_submit,
        {"await_decision": "await_admin_decision", "skip": "guardrail_filter"},
    )
    graph.add_conditional_edges(
        "await_admin_decision",
        route_after_admin_decision,
        {"approved": "store_via_mcp", "rejected": "reject_notify"},
    )
    graph.add_edge("store_via_mcp", "guardrail_filter")
    graph.add_edge("reject_notify", "guardrail_filter")
    graph.add_edge("handle_awaiting_admin", "guardrail_filter")
    graph.add_edge("handle_reservation_status", "guardrail_filter")
    graph.add_edge("handle_dynamic_info", "guardrail_filter")
    graph.add_edge("handle_static_info", "guardrail_filter")
    graph.add_edge("guardrail_filter", END)

    return graph.compile(checkpointer=get_checkpointer())


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def resume_with_admin_decision(session_id: str, decision: str) -> ChatState:
    """Resume a graph thread paused at `await_admin_decision` with the
    administrator's decision ("approved"/"rejected"). This is what makes the
    human-in-the-loop pause a real pause rather than a simulated one: the
    thread's state was checkpointed to SQLite when it hit `interrupt()`, so
    this call can resume it from an entirely separate process/request."""
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": session_id}}
    return graph.invoke(Command(resume={"decision": decision}), config=config)
