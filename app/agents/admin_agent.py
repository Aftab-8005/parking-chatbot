"""The second agent: a human-in-the-loop agent that talks to the administrator.

Responsibilities (Stage 2):
  1. Draft a reservation-approval request (`draft_approval_message`) using a
     LangChain `ChatPromptTemplate` + `ChatOpenAI` chain, with a deterministic
     template fallback if the LLM call fails (e.g. no API key available).
  2. Send that request to the administrator (`request_approval`) via the
     email notification channel (falls back to logging if SMTP isn't
     configured) and over the admin REST API (`app/api/admin_routes.py`),
     which is where the administrator actually records their decision.
  3. Interpret free-text admin replies into a structured decision
     (`parse_decision`), for channels (e.g. "reply to this email") where the
     administrator doesn't use the structured REST payload directly.
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.notifications.email_client import send_email

logger = logging.getLogger("parking_chatbot.admin_agent")

_DRAFT_SYSTEM_PROMPT = """You are an assistant that drafts short, clear internal notification
emails for a parking facility administrator. Given a reservation request, write a brief email
body (3-5 sentences) asking the administrator to approve or reject it. Mention the reservation
reference number, the car number, and the requested time window. Do not invent any details beyond
what is given. Do not add a greeting/signature, just the body text."""

_draft_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _DRAFT_SYSTEM_PROMPT),
        ("human", "{reservation_summary}"),
    ]
)

_APPROVE_WORDS = {"approve", "approved", "yes", "confirm", "confirmed", "accept", "accepted", "ok"}
_REJECT_WORDS = {"reject", "rejected", "no", "deny", "denied", "refuse", "refused", "decline", "declined"}


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=settings.openai_chat_model, api_key=settings.openai_api_key, temperature=0)


def _reservation_summary(reservation: dict) -> str:
    return (
        f"Reservation #{reservation['id']}: {reservation['first_name']} {reservation['last_name']}, "
        f"car {reservation['car_number']}, from {reservation['start_time']} to {reservation['end_time']}."
    )


def _fallback_message(reservation: dict) -> str:
    return (
        f"A new parking reservation is awaiting your approval.\n\n"
        f"{_reservation_summary(reservation)}\n\n"
        f"Approve or reject it via the admin API: "
        f"POST /admin/reservations/{reservation['id']}/decision "
        f'{{"decision": "approved"}} or {{"decision": "rejected"}}.'
    )


def draft_approval_message(reservation: dict, llm: ChatOpenAI | None = None) -> str:
    """Draft the body of the approval-request notification. Falls back to a
    deterministic template if the LLM call raises (missing/invalid API key,
    network error, etc.) so the human-in-the-loop flow never gets stuck on an
    LLM outage."""
    try:
        llm = llm or get_llm()
        messages = _draft_prompt.invoke({"reservation_summary": _reservation_summary(reservation)})
        response = llm.invoke(messages)
        content = (response.content or "").strip()
        return content or _fallback_message(reservation)
    except Exception:
        logger.warning("Falling back to template approval message for reservation #%s", reservation.get("id"))
        return _fallback_message(reservation)


def request_approval(reservation: dict, llm: ChatOpenAI | None = None) -> bool:
    """Notify the administrator that a reservation needs approval.

    Returns True if an email was actually sent, False if it was only logged
    (no SMTP configured) -- in both cases the reservation is still waiting in
    the DB / orchestrator graph for the admin's decision via the REST API.
    """
    subject = f"[Parking] Reservation #{reservation['id']} awaiting your approval"
    body = draft_approval_message(reservation, llm=llm)
    return send_email(settings.admin_email, subject, body)


def parse_decision(text: str) -> str | None:
    """Interpret a free-text administrator reply as 'approved', 'rejected',
    or None if it can't be confidently classified."""
    normalized = text.strip().lower()
    words = set(normalized.replace(",", " ").replace(".", " ").split())
    if words & _APPROVE_WORDS:
        return "approved"
    if words & _REJECT_WORDS:
        return "rejected"
    return None
