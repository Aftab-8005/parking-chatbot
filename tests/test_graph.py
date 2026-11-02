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


def test_handle_reservation_starts_slot_filling():
    state = new_state("I want to reserve a spot")
    state["intent"] = "reservation"
    state = chatbot_graph.handle_reservation(state)
    assert state["reservation_in_progress"] is True
    assert "first name" in state["response"].lower()


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


def test_build_graph_full_flow_dynamic_info(monkeypatch):
    monkeypatch.setattr(
        chatbot_graph.dynamic_service,
        "get_availability",
        lambda: {"total_spaces": 100, "available_spaces": 10},
    )
    graph = chatbot_graph.build_graph()
    state = new_state("How many spaces are available?")
    result = graph.invoke(state)
    assert result["intent"] == "dynamic_info"
    assert "10" in result["response"]
