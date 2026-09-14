"""Audit event schema (EP-08-T02, README.md §27).

Adopts the IC/NOC/GRL taxonomy from the Agent Platform OCI reference
(ADR-022, docs/research/hoshikawa-agent-platform-oci.md) as the
`EventEnvelope.category` classification, rather than inventing a parallel
one: IC (Indicador de Controle/negócio-jornada), NOC (operacional/erro), GRL
(guardrail/governança). `decision_id`/`policy_decision_id`/`entitlement_version`
(ADR-017, EP-08-T03) travel as first-class correlation fields on every event,
not as opaque payload keys, so a consumer can join events across the chain
without parsing `payload`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

_SENSITIVE_KEY_MARKERS = ("token", "secret", "password", "authorization", "credential")


class EventCategory(StrEnum):
    """README.md §27 event classes, mapped onto the Hoshikawa IC/NOC/GRL vocabulary."""

    IC = "ic"
    """Indicador de Controle / negócio-jornada: the call progressed normally
    (e.g. `client_authenticated`, `tool_call_allowed`)."""

    NOC = "noc"
    """Operacional/erro: an availability/infra failure, not a policy decision
    (e.g. `pdp_unavailable`, `backend_credential_unavailable`)."""

    GRL = "grl"
    """Guardrail/governança: an entitlement/policy boundary was enforced or
    tested (e.g. `tool_call_denied`, `tools_list_filtered`, `bypass_attempt_detected`)."""


def _sanitize(value: Any) -> Any:
    """Never let a token/secret value reach a sink (§27, "Não registrar").

    Recurses into mappings/sequences; any mapping key whose lowercased name
    contains a marker in `_SENSITIVE_KEY_MARKERS` has its value replaced by a
    `sha256:<hex>` reference instead of being dropped -- a reader can still
    tell two events referenced the *same* secret without ever seeing it.
    """
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, inner in value.items():
            if isinstance(key, str) and any(
                marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS
            ):
                digest = hashlib.sha256(str(inner).encode("utf-8")).hexdigest()
                sanitized[key] = f"sha256:{digest}"
            else:
                sanitized[key] = _sanitize(inner)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: str
    category: EventCategory
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    client_id: str | None = None
    profile_name: str | None = None
    tool: str | None = None
    reason_code: str | None = None

    decision_id: str | None = None
    policy_decision_id: str | None = None
    entitlement_version: str | None = None
    policy_version: str | None = None
    mcp_request_id: str | None = None
    trace_id: str | None = None

    payload: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Sanitize post-construction so every construction path (including
        # `model_validate` deserialization from a sink) gets the same guarantee.
        self.payload = _sanitize(self.payload)
