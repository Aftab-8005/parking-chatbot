from app.security.guardrails import contains_pii, is_safe_for_vector_store, redact_pii, scan_for_pii


def test_scan_for_pii_detects_email_and_phone():
    text = "Contact John at john.doe@example.com or call 555-123-4567."
    matches = scan_for_pii(text)
    categories = {m.category for m in matches}
    assert "email" in categories
    assert "phone" in categories


def test_contains_pii_false_for_clean_static_text():
    text = "The parking facility operates every day from 06:00 to 23:00."
    assert contains_pii(text) is False


def test_redact_pii_masks_email():
    text = "Reach support at support@parking.com for help."
    redacted = redact_pii(text)
    assert "support@parking.com" not in redacted
    assert "[REDACTED]" in redacted


def test_is_safe_for_vector_store_rejects_document_with_credit_card():
    text = "Card number 4111111111111111 was used for payment."
    assert is_safe_for_vector_store(text) is False


def test_is_safe_for_vector_store_accepts_general_knowledge():
    text = "City Center Parking has 100 standard parking spaces for passenger cars."
    assert is_safe_for_vector_store(text) is True
