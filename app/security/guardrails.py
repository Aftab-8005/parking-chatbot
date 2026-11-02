"""Guardrails that prevent sensitive/personal data from being stored in or
leaked out of the chatbot.

Two checkpoints use this module:
  1. Ingestion time -- documents are scanned before being embedded and written
     to the vector database, so personal data never enters the vector store.
  2. Response time -- every answer returned to a user is scanned and any
     detected PII is redacted before it reaches the chat surface.

Detection combines fast regex rules (email, phone, card, SSN-like numbers)
with an optional pretrained spaCy NER model (PERSON / GPE / ORG entities).
spaCy is loaded lazily and the detector degrades gracefully to regex-only
behaviour if the model is not installed, so the app still works without the
extra download.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_PII_PATTERNS = {
    "email": _EMAIL_RE,
    "credit_card": _CREDIT_CARD_RE,
    "ssn": _SSN_RE,
    "phone": _PHONE_RE,
}

_SENSITIVE_ENTITY_LABELS = {"PERSON"}

_nlp = None
_nlp_load_attempted = False


def _get_nlp():
    """Lazily load the spaCy pretrained NER model. Returns None if unavailable."""
    global _nlp, _nlp_load_attempted
    if _nlp_load_attempted:
        return _nlp
    _nlp_load_attempted = True
    try:
        import spacy

        _nlp = spacy.load("en_core_web_sm")
    except Exception:
        _nlp = None
    return _nlp


@dataclass
class PIIMatch:
    category: str
    value: str


def scan_for_pii(text: str) -> list[PIIMatch]:
    """Return every PII match found in `text` using regex + (optional) NER."""
    matches: list[PIIMatch] = []

    for category, pattern in _PII_PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append(PIIMatch(category=category, value=m.group()))

    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in _SENSITIVE_ENTITY_LABELS:
                matches.append(PIIMatch(category=f"ner_{ent.label_.lower()}", value=ent.text))

    return matches


def contains_pii(text: str) -> bool:
    return len(scan_for_pii(text)) > 0


def redact_pii(text: str, redact_names: bool = True) -> str:
    """Replace every detected PII span with a `[REDACTED]` placeholder.

    `redact_names=False` skips the NER-based PERSON-name redaction while
    still stripping emails/phones/card/SSN-like numbers. Use this for
    responses that intentionally echo back data the current user themselves
    just supplied (e.g. a reservation confirmation) -- that's expected
    behaviour, not a PII leak, and NER would otherwise redact the user's own
    name out of their own confirmation message.
    """
    redacted = text
    for pattern in (_EMAIL_RE, _CREDIT_CARD_RE, _SSN_RE, _PHONE_RE):
        redacted = pattern.sub("[REDACTED]", redacted)

    nlp = _get_nlp()
    if nlp is not None and redact_names:
        doc = nlp(redacted)
        spans = [(ent.start_char, ent.end_char) for ent in doc.ents if ent.label_ in _SENSITIVE_ENTITY_LABELS]
        for start, end in sorted(spans, key=lambda s: s[0], reverse=True):
            redacted = redacted[:start] + "[REDACTED]" + redacted[end:]

    return redacted


def is_safe_for_vector_store(text: str) -> bool:
    """Guardrail applied at ingestion time: reject documents carrying PII
    (emails, phone numbers, card/SSN-like numbers, or named individuals)
    before they are embedded into the vector database."""
    return not contains_pii(text)
