"""PII/secret redaction before Langfuse export (EP-13-T03, README.md §27)."""

from __future__ import annotations

from emcp_bus.common.pii_redaction import redact_mapping, redact_text


def test_redact_text_masks_an_email() -> None:
    result = redact_text("contact me at jane.doe@example.com please")
    assert result == "contact me at [REDACTED] please"


def test_redact_text_masks_a_cpf() -> None:
    assert redact_text("cpf: 123.456.789-01") == "cpf: [REDACTED]"


def test_redact_text_masks_a_phone_number() -> None:
    assert redact_text("call +55 11 99999-8888") == "call [REDACTED]"


def test_redact_text_leaves_non_pii_text_unchanged() -> None:
    text = "the customer wants a quote for sku-100"
    assert redact_text(text) == text


def test_redact_mapping_redacts_a_sensitive_key_outright() -> None:
    result = redact_mapping({"email": "jane.doe@example.com", "amount": 100})

    assert result["email"] == "[REDACTED]"
    assert result["amount"] == 100


def test_redact_mapping_scans_string_values_for_pii_patterns() -> None:
    result = redact_mapping({"note": "reach jane.doe@example.com for details"})

    assert result["note"] == "reach [REDACTED] for details"


def test_redact_mapping_recurses_into_nested_dicts() -> None:
    result = redact_mapping({"customer": {"email": "jane.doe@example.com", "name": "Jane"}})

    assert result["customer"]["email"] == "[REDACTED]"
    assert result["customer"]["name"] == "Jane"


def test_redact_mapping_recurses_into_lists_of_dicts_and_strings() -> None:
    result = redact_mapping(
        {"notes": ["contact jane.doe@example.com", {"email": "other@example.com"}]}
    )

    assert result["notes"][0] == "contact [REDACTED]"
    assert result["notes"][1]["email"] == "[REDACTED]"
