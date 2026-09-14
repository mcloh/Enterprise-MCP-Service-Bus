"""PII/secret redaction before any Langfuse trace export (EP-13-T03, README.md
§27 "Não registrar", seção 6 do superprompt: mandatory before any Langfuse
export).

Pattern-based, not a claim of exhaustive PII detection -- covers the shapes
the RI's own example agent's mocked data can plausibly produce (email, a
Brazilian CPF-shaped number, a phone number) plus the same sensitive-key
heuristic already used for audit payloads (`emcp_bus.audit.models._sanitize`).
A production deployment handling real customer data would replace/extend
the patterns here, not the call sites that use this module -- `redact_text`/
`redact_mapping` are the whole contract.
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CPF_PATTERN = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_PHONE_PATTERN = re.compile(r"\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}\b")

_SENSITIVE_KEY_MARKERS = ("email", "cpf", "ssn", "phone", "token", "secret", "password")

_REDACTION_MARK = "[REDACTED]"


def redact_text(text: str) -> str:
    redacted = _EMAIL_PATTERN.sub(_REDACTION_MARK, text)
    redacted = _CPF_PATTERN.sub(_REDACTION_MARK, redacted)
    redacted = _PHONE_PATTERN.sub(_REDACTION_MARK, redacted)
    return redacted


def redact_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    """Recurses into nested dicts/lists; a key that looks sensitive by name
    is redacted outright (value never inspected), everything else has its
    string values pattern-scanned via `redact_text`."""
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(key, str) and any(marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS):
            result[key] = _REDACTION_MARK
        elif isinstance(value, dict):
            result[key] = redact_mapping(value)
        elif isinstance(value, list):
            result[key] = [
                redact_mapping(item)
                if isinstance(item, dict)
                else (redact_text(item) if isinstance(item, str) else item)
                for item in value
            ]
        elif isinstance(value, str):
            result[key] = redact_text(value)
        else:
            result[key] = value
    return result
