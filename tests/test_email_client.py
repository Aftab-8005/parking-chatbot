from unittest.mock import MagicMock

from app.notifications import email_client


def test_send_email_falls_back_to_logging_when_smtp_not_configured(monkeypatch):
    monkeypatch.setattr(email_client.settings, "smtp_host", "")
    sent = email_client.send_email("admin@example.com", "Subject", "Body")
    assert sent is False


def test_send_email_falls_back_to_logging_when_no_recipient(monkeypatch):
    monkeypatch.setattr(email_client.settings, "smtp_host", "smtp.example.com")
    sent = email_client.send_email("", "Subject", "Body")
    assert sent is False


def test_send_email_sends_via_smtp_when_configured(monkeypatch):
    monkeypatch.setattr(email_client.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_client.settings, "smtp_port", 587)
    monkeypatch.setattr(email_client.settings, "smtp_user", "user")
    monkeypatch.setattr(email_client.settings, "smtp_password", "pass")
    monkeypatch.setattr(email_client.settings, "smtp_use_tls", True)

    fake_server = MagicMock()
    fake_smtp_cls = MagicMock()
    fake_smtp_cls.return_value.__enter__.return_value = fake_server
    monkeypatch.setattr(email_client.smtplib, "SMTP", fake_smtp_cls)

    sent = email_client.send_email("admin@example.com", "Subject", "Body")

    assert sent is True
    fake_server.starttls.assert_called_once()
    fake_server.login.assert_called_once_with("user", "pass")
    fake_server.send_message.assert_called_once()
