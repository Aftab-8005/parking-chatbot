import uuid
from unittest.mock import MagicMock

import pytest

from app.graph import chatbot_graph
from app.graph.state import new_state


def test_classify_intent_detects_reservation_keyword():
    state = new_state("I want to book a reservation")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation"


def test_classify_intent_detects_dynamic_info_keyword():
    state = new_state("What is the price per hour?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "dynamic_info"


def test_classify_intent_continues_reservation_in_progress():
    state = new_state("John", previous={"reservation_in_progress": True, "reservation_slots": {}})
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation"


def test_classify_intent_routes_awaiting_admin_when_pending():
    state = new_state("anything", previous={"reservation_status": "pending_admin_approval", "request_id": "r1"})
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "awaiting_admin"


def test_handle_reservation_starts_slot_filling():
    state = new_state("I want to reserve a spot")
    state["intent"] = "reservation"
    state = chatbot_graph.handle_reservation(state)
    assert state["reservation_in_progress"] is True
    assert "first name" in state["response"].lower()


def test_handle_reservation_falls_back_to_deterministic_slot_when_extraction_fails(monkeypatch):
    monkeypatch.setattr(chatbot_graph, "extract_and_merge", lambda slots, message, now: slots)
    state = new_state("Jane", previous={"reservation_in_progress": True, "reservation_slots": {}})
    state["intent"] = "reservation"
    state = chatbot_graph.handle_reservation(state)
    assert state["reservation_slots"]["first_name"] == "Jane"


def test_route_after_reservation_submits_when_complete():
    state = new_state("anything")
    state["reservation_complete"] = True
    assert chatbot_graph.route_after_reservation(state) == "submit"


def test_route_after_reservation_continues_when_incomplete():
    state = new_state("anything")
    state["reservation_complete"] = False
    assert chatbot_graph.route_after_reservation(state) == "continue"


def test_submit_to_admin_creates_reservation_and_request(monkeypatch):
    monkeypatch.setattr(chatbot_graph.dynamic_service, "find_conflicting_reservation", lambda *a: None)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_reservation", lambda **kw: 42)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_admin_request", lambda reservation_id: "req-abc123")

    state = new_state("anything")
    state["reservation_slots"] = {
        "first_name": "Jane",
        "last_name": "Doe",
        "car_number": "AB1234",
        "start_time": "2026-11-25T10:00:00",
        "end_time": "2026-11-25T12:00:00",
    }
    config = {"configurable": {"thread_id": "session-1"}}

    state = chatbot_graph.submit_to_admin(state, config)

    assert state["reservation_id"] == 42
    assert state["request_id"] == "req-abc123"
    assert state["reservation_status"] == "pending_admin_approval"
    assert "administrator" in state["response"].lower()


def test_submit_to_admin_blocks_overlapping_double_booking(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "find_conflicting_reservation",
        lambda car, start, end: {"id": 1, "status": "approved", "start_time": start, "end_time": end},
    )
    created = {"called": False}
    monkeypatch.setattr(
        chatbot_graph.dynamic_service, "create_reservation", lambda **kw: created.update(called=True) or 1
    )

    state = new_state("anything")
    state["reservation_slots"] = {
        "first_name": "Jane",
        "last_name": "Doe",
        "car_number": "AB1234",
        "start_time": "2026-11-25T10:00:00",
        "end_time": "2026-11-25T12:00:00",
    }
    config = {"configurable": {"thread_id": "session-dup"}}

    state = chatbot_graph.submit_to_admin(state, config)

    assert created["called"] is False
    assert state.get("request_id") is None
    assert "already has a reservation" in state["response"]
    assert chatbot_graph.route_after_submit(state) == "skip"


def test_route_after_admin_decision_approved_vs_rejected():
    approved_state = new_state("x")
    approved_state["reservation_status"] = "approved"
    assert chatbot_graph.route_after_admin_decision(approved_state) == "approved"

    rejected_state = new_state("x")
    rejected_state["reservation_status"] = "rejected"
    assert chatbot_graph.route_after_admin_decision(rejected_state) == "rejected"


def test_store_via_mcp_success_marks_reservation_stored(monkeypatch):
    reservation = MagicMock(first_name="Jane", last_name="Doe", car_number="AB1234")
    monkeypatch.setattr(chatbot_graph.dynamic_service, "get_reservation", lambda rid: reservation)
    monkeypatch.setattr(chatbot_graph, "save_confirmed_reservation", lambda **kw: {"stored": True})
    marked = {}
    monkeypatch.setattr(
        chatbot_graph.dynamic_service, "mark_reservation_stored", lambda rid: marked.setdefault("id", rid)
    )

    state = new_state("x")
    state["reservation_id"] = 1
    state["request_id"] = "req-12345678"
    state = chatbot_graph.store_via_mcp(state)

    assert state["reservation_status"] == "stored"
    assert marked["id"] == 1
    assert "approved" in state["response"].lower()


def test_store_via_mcp_failure_marks_pending_storage(monkeypatch):
    reservation = MagicMock(first_name="Jane", last_name="Doe", car_number="AB1234")
    monkeypatch.setattr(chatbot_graph.dynamic_service, "get_reservation", lambda rid: reservation)

    def boom(**kwargs):
        raise chatbot_graph.McpUnavailableError("down")

    monkeypatch.setattr(chatbot_graph, "save_confirmed_reservation", boom)
    marked = {}
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "mark_reservation_pending_storage",
        lambda rid: marked.setdefault("id", rid),
    )

    state = new_state("x")
    state["reservation_id"] = 1
    state["request_id"] = "req-12345678"
    state = chatbot_graph.store_via_mcp(state)

    assert state["reservation_status"] == "approved_pending_storage"
    assert marked["id"] == 1
    assert "retried" in state["response"].lower()


def test_retry_mcp_storage_succeeds_after_mcp_recovers(monkeypatch):
    reservation = MagicMock(first_name="Jane", last_name="Doe", car_number="AB1234")
    monkeypatch.setattr(chatbot_graph.dynamic_service, "get_reservation", lambda rid: reservation)
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "get_admin_request",
        lambda rid: {"reservation_id": 1, "reservation_status": "approved_pending_storage"},
    )
    monkeypatch.setattr(chatbot_graph, "save_confirmed_reservation", lambda **kw: {"stored": True})
    monkeypatch.setattr(chatbot_graph.dynamic_service, "mark_reservation_stored", lambda rid: None)

    status, message = chatbot_graph.retry_mcp_storage("req-12345678")
    assert status == "stored"
    assert "approved" in message.lower()


def test_retry_mcp_storage_raises_for_unknown_request(monkeypatch):
    monkeypatch.setattr(chatbot_graph.dynamic_service, "get_admin_request", lambda rid: None)
    with pytest.raises(ValueError):
        chatbot_graph.retry_mcp_storage("missing")


def test_reject_notify_sets_rejection_message():
    state = new_state("x")
    state["request_id"] = "req-12345678"
    state = chatbot_graph.reject_notify(state)
    assert "not approved" in state["response"].lower()


def test_classify_intent_detects_status_question_with_hash_reference():
    state = new_state("Is reference number #f853d9e2 approved?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_classify_intent_detects_status_question_with_bare_reference():
    state = new_state("Is f853d9e2 approved?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_classify_intent_detects_status_question_without_reference():
    state = new_state("Has my parking reservation been approved?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_extract_reference_number_supports_hash_and_bare_forms():
    assert chatbot_graph.extract_reference_number("Check #f853d9e2 please") == "f853d9e2"
    assert chatbot_graph.extract_reference_number("Check f853d9e2 please") == "f853d9e2"
    assert chatbot_graph.extract_reference_number("No reference here") is None


def test_handle_reservation_status_pending(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "find_admin_request_by_reference",
        lambda ref: {"request_id": "f853d9e2-aaaa-bbbb-cccc-dddddddddddd", "status": "pending", "reservation_status": "pending_admin_approval"},
    )
    state = new_state("Is #f853d9e2 approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "pending administrator approval" in state["response"].lower()


def test_handle_reservation_status_approved(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "find_admin_request_by_reference",
        lambda ref: {"request_id": "f853d9e2-aaaa-bbbb-cccc-dddddddddddd", "status": "approved", "reservation_status": "approved"},
    )
    state = new_state("Is #f853d9e2 approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "has been approved" in state["response"].lower()


def test_handle_reservation_status_approved_pending_storage(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "find_admin_request_by_reference",
        lambda ref: {
            "request_id": "f853d9e2-aaaa-bbbb-cccc-dddddddddddd",
            "status": "approved",
            "reservation_status": "approved_pending_storage",
        },
    )
    state = new_state("Is #f853d9e2 approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "confirmation storage is still pending" in state["response"].lower()


def test_handle_reservation_status_rejected(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "find_admin_request_by_reference",
        lambda ref: {"request_id": "f853d9e2-aaaa-bbbb-cccc-dddddddddddd", "status": "rejected", "reservation_status": "rejected"},
    )
    state = new_state("Is #f853d9e2 approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "has been rejected" in state["response"].lower()


def test_handle_reservation_status_unknown_reference(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service, "find_admin_request_by_reference", lambda ref: None
    )
    state = new_state("Is #doesnotexist approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "couldn't find a reservation" in state["response"].lower()


def test_classify_intent_detects_status_question_with_unknown_hash_reference():
    state = new_state("Is #doesnotexist approved?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_classify_intent_detects_status_question_bare_reference_phrased_as_what_is_status():
    state = new_state("What is the status of f853d9e2?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_classify_intent_detects_status_question_about_my_reservation_without_reference():
    state = new_state("What is the status of my reservation?")
    state = chatbot_graph.classify_intent(state)
    assert state["intent"] == "reservation_status"


def test_handle_reservation_status_without_reference_asks_for_one():
    state = new_state("Has my parking reservation been approved?")
    state["intent"] = "reservation_status"
    state = chatbot_graph.handle_reservation_status(state)
    assert "reference number" in state["response"].lower()


def test_handle_dynamic_info_uses_dynamic_service(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "get_pricing",
        lambda: {"hourly_price": 2.0, "daily_price": 15.0, "currency": "USD"},
    )
    state = new_state("What is the price?")
    state["intent"] = "dynamic_info"
    state = chatbot_graph.handle_dynamic_info(state)
    assert "2.0" in state["response"]


def test_handle_static_info_degrades_gracefully_on_rag_failure(monkeypatch):
    def boom(question):
        raise RuntimeError("Qdrant/OpenAI unavailable")

    monkeypatch.setattr(chatbot_graph, "answer_static_question", boom)
    state = new_state("Where are you located?")
    state["intent"] = "static_info"
    state = chatbot_graph.handle_static_info(state)
    assert "can't look that up" in state["response"]


def test_guardrail_filter_redacts_response():
    state = new_state("anything")
    state["intent"] = "static_info"
    state["response"] = "Contact me at test@example.com"
    state = chatbot_graph.guardrail_filter(state)
    assert "test@example.com" not in state["response"]


def test_guardrail_filter_does_not_redact_users_own_name_in_reservation_confirmation():
    state = new_state("anything")
    state["intent"] = "reservation"
    state["response"] = "Thanks Alex Smith, your reservation for car XY-9999 is submitted."
    state = chatbot_graph.guardrail_filter(state)
    assert "Alex Smith" in state["response"]


def test_guardrail_filter_still_redacts_names_for_static_info():
    state = new_state("anything")
    state["intent"] = "static_info"
    state["response"] = "Our manager Alex Smith can help you."
    state = chatbot_graph.guardrail_filter(state)
    assert "Alex Smith" not in state["response"]


def test_build_graph_full_flow_dynamic_info(monkeypatch, tmp_path):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "get_availability",
        lambda: {"total_spaces": 100, "available_spaces": 10},
    )
    graph = chatbot_graph.build_graph()
    config = {"configurable": {"thread_id": f"test-thread-dynamic-{uuid.uuid4()}"}}
    result = graph.invoke({"user_message": "How many spaces are available?"}, config=config)
    assert result["intent"] == "dynamic_info"
    assert "10" in result["response"]


def test_full_reservation_flow_pauses_for_admin_then_resumes_on_approval(monkeypatch):
    reservation = MagicMock(
        first_name="Jane", last_name="Doe", car_number="AB1234",
        start_time="2026-11-25T10:00:00", end_time="2026-11-25T12:00:00",
    )
    monkeypatch.setattr(chatbot_graph.dynamic_service, "find_conflicting_reservation", lambda *a: None)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_reservation", lambda **kw: 1)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_admin_request", lambda reservation_id: "req-99999999")
    monkeypatch.setattr(chatbot_graph.dynamic_service, "get_reservation", lambda rid: reservation)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "mark_reservation_stored", lambda rid: None)
    monkeypatch.setattr(chatbot_graph, "save_confirmed_reservation", lambda **kw: {"stored": True})
    monkeypatch.setattr(
        chatbot_graph, "extract_and_merge", lambda slots, message, now: slots
    )

    graph = chatbot_graph.build_graph()
    thread = f"test-thread-reservation-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread}}

    graph.invoke({"user_message": "I want to reserve a spot"}, config=config)
    graph.invoke({"user_message": "Jane"}, config=config)
    graph.invoke({"user_message": "Doe"}, config=config)
    graph.invoke({"user_message": "AB1234"}, config=config)
    graph.invoke({"user_message": "2026-11-25 10:00"}, config=config)
    paused = graph.invoke({"user_message": "2026-11-25 12:00"}, config=config)

    assert paused.get("__interrupt__")
    assert paused["reservation_status"] == "pending_admin_approval"

    resumed = chatbot_graph.resume_with_admin_decision(thread, "approved")
    assert resumed["reservation_status"] == "stored"
    assert "approved" in resumed["response"].lower()


def test_overlap_rejection_allows_fresh_reservation_same_thread(monkeypatch):
    """TEST 1 & 2: after a double-booking rejection, saying 'I want to make
    another reservation' in the SAME thread must start a clean flow -- not
    reuse the previous name/plate/time, and not require a new thread_id."""
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_reservation", lambda **kw: 1)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_admin_request", lambda reservation_id: "req-11111111")
    monkeypatch.setattr(chatbot_graph, "extract_and_merge", lambda slots, message, now: slots)

    def conflicting_only_for_test123(car, start, end):
        if car == "TEST123":
            return {"id": 1, "status": "approved", "start_time": start, "end_time": end}
        return None

    monkeypatch.setattr(chatbot_graph.dynamic_service, "find_conflicting_reservation", conflicting_only_for_test123)

    graph = chatbot_graph.build_graph()
    thread = f"test-thread-overlap-reset-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread}}

    graph.invoke({"user_message": "I want a reservation"}, config=config)
    graph.invoke({"user_message": "Rahul"}, config=config)
    graph.invoke({"user_message": "Sharma"}, config=config)
    graph.invoke({"user_message": "TEST123"}, config=config)
    graph.invoke({"user_message": "2026-12-10 10:00"}, config=config)
    rejected = graph.invoke({"user_message": "2026-12-10 14:00"}, config=config)

    assert "already has a reservation" in rejected["response"]
    assert rejected["reservation_in_progress"] is False
    assert rejected["reservation_slots"] == {}

    # Same thread, no refresh/new session -- user asks for another reservation.
    fresh = graph.invoke({"user_message": "I want to make another reservation"}, config=config)
    assert fresh["intent"] == "reservation"
    assert fresh["reservation_in_progress"] is True
    assert "first name" in fresh["response"].lower()
    assert fresh["reservation_slots"].get("first_name") is None
    assert fresh["reservation_slots"].get("car_number") is None

    # TEST 2: a different vehicle can now complete independently, same thread.
    graph.invoke({"user_message": "Jane"}, config=config)
    graph.invoke({"user_message": "Doe"}, config=config)
    graph.invoke({"user_message": "NEW456"}, config=config)
    graph.invoke({"user_message": "2026-12-11 09:00"}, config=config)
    second = graph.invoke({"user_message": "2026-12-11 11:00"}, config=config)

    assert second["reservation_status"] == "pending_admin_approval"
    assert second["reservation_slots"]["car_number"] == "NEW456"
    assert second["reservation_slots"]["first_name"] == "Jane"


def test_invalid_time_mid_flow_then_restart_does_not_reuse_old_slots(monkeypatch):
    """TEST 3: a start>end validation failure keeps the slot-filling flow
    continuable (normal correction UX), but an explicit 'another reservation'
    request afterwards still discards the stale/invalid slots."""
    monkeypatch.setattr(chatbot_graph, "extract_and_merge", lambda slots, message, now: slots)

    graph = chatbot_graph.build_graph()
    thread = f"test-thread-invalid-time-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread}}

    graph.invoke({"user_message": "I want a reservation"}, config=config)
    graph.invoke({"user_message": "Rahul"}, config=config)
    graph.invoke({"user_message": "Sharma"}, config=config)
    graph.invoke({"user_message": "TEST123"}, config=config)
    graph.invoke({"user_message": "2026-12-10 14:00"}, config=config)
    invalid = graph.invoke({"user_message": "2026-12-10 10:00"}, config=config)

    assert "end time must be after the start time" in invalid["response"].lower()
    assert invalid["reservation_in_progress"] is True
    assert invalid["reservation_slots"]["car_number"] == "TEST123"

    restarted = graph.invoke({"user_message": "I want to reserve parking at Mall Parking"}, config=config)
    assert restarted["reservation_in_progress"] is True
    assert restarted["reservation_slots"].get("car_number") is None
    assert restarted["reservation_slots"].get("start_time") is None
    assert "first name" in restarted["response"].lower()


def test_normal_slot_filling_is_not_reset_prematurely(monkeypatch):
    """TEST 4: supplying just the first name must keep the flow active and
    ask for the surname next -- no reset."""
    monkeypatch.setattr(chatbot_graph, "extract_and_merge", lambda slots, message, now: slots)

    graph = chatbot_graph.build_graph()
    thread = f"test-thread-normal-slots-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread}}

    graph.invoke({"user_message": "I want a reservation"}, config=config)
    after_name = graph.invoke({"user_message": "Rahul"}, config=config)

    assert after_name["reservation_in_progress"] is True
    assert after_name["reservation_slots"]["first_name"] == "Rahul"
    assert "surname" in after_name["response"].lower()


def test_full_reservation_flow_rejected_does_not_call_mcp(monkeypatch):
    mcp_called = {"called": False}

    def fake_mcp(**kwargs):
        mcp_called["called"] = True
        return {"stored": True}

    monkeypatch.setattr(chatbot_graph.dynamic_service, "find_conflicting_reservation", lambda *a: None)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_reservation", lambda **kw: 2)
    monkeypatch.setattr(chatbot_graph.dynamic_service, "create_admin_request", lambda reservation_id: "req-88888888")
    monkeypatch.setattr(chatbot_graph, "save_confirmed_reservation", fake_mcp)
    monkeypatch.setattr(chatbot_graph, "extract_and_merge", lambda slots, message, now: slots)

    graph = chatbot_graph.build_graph()
    thread = f"test-thread-rejection-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread}}

    graph.invoke({"user_message": "I want to reserve a spot"}, config=config)
    graph.invoke({"user_message": "Jane"}, config=config)
    graph.invoke({"user_message": "Doe"}, config=config)
    graph.invoke({"user_message": "AB1234"}, config=config)
    graph.invoke({"user_message": "2026-11-25 10:00"}, config=config)
    graph.invoke({"user_message": "2026-11-25 12:00"}, config=config)

    resumed = chatbot_graph.resume_with_admin_decision(thread, "rejected")
    assert resumed["reservation_status"] == "rejected"
    assert "not approved" in resumed["response"].lower()
    assert mcp_called["called"] is False
