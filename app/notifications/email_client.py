"""Thin SMTP wrapper used to notify the administrator about a reservation.

If `settings.smtp_host` is not configured (local dev, CI, tests) this degrades
gracefully to logging the message instead of raising — the rest of the
human-in-the-loop flow (writing the reservation to the DB, waiting for an
admin decision via the REST API) still works without a real mail server.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("parking_chatbot.notifications")


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send an email via SMTP. Returns True if an email was actually sent,
    False if it was only logged (no SMTP server configured)."""
    if not settings.smtp_host or not to_address:
        logger.info("SMTP not configured; logging notification instead.\nTo: %s\nSubject: %s\n%s", to_address, subject, body)
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
    return True
