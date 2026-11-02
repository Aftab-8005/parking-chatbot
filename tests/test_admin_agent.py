from unittest.mock import MagicMock

from app.agents import admin_agent

_RESERVATION = {
    "id": 42,
    "first_name": "Jane",
    "last_name": "Doe",
    "car_number": "AB-1234",
    "start_time": "2026-11-05 09:00",
    "end_time": "2026-11-05 17:00",
}


def test_draft_approval_message_uses_llm_response():
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="Please approve reservation #42.")
    message = admin_agent.draft_approval_message(_RESERVATION, llm=fake_llm)
    assert message == "Please approve reservation #42."


def test_draft_approval_message_falls_back_on_llm_error():
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("no API key")
    message = admin_agent.draft_approval_message(_RESERVATION, llm=fake_llm)
    assert "#42" in message
    assert "AB-1234" in message


def test_request_approval_sends_email_to_admin(monkeypatch):
    monkeypatch.setattr(admin_agent.settings, "admin_email", "admin@example.com")
    sent_args = {}

    def fake_send_email(to_address, subject, body):
        sent_args.update(to_address=to_address, subject=subject, body=body)
        return True

    monkeypatch.setattr(admin_agent, "send_email", fake_send_email)
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="Approve #42 please.")

    result = admin_agent.request_approval(_RESERVATION, llm=fake_llm)

    assert result is True
    assert sent_args["to_address"] == "admin@example.com"
    assert "#42" in sent_args["subject"]


def test_parse_decision_recognizes_approval_words():
    assert admin_agent.parse_decision("Yes, approve it") == "approved"
    assert admin_agent.parse_decision("please reject this one") == "rejected"


def test_parse_decision_returns_none_for_ambiguous_text():
    assert admin_agent.parse_decision("what time is it?") is None
