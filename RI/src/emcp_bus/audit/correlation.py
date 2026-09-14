"""End-to-end correlation (EP-08-T03, README.md §27/§28, ADR-017).

One `DecisionCorrelation` is created per `tools/call` attempt and threaded
through: the PDP decision, the audit events it produces, and the current
OTel span (as attributes) -- so a single `decision_id` recovers every event
of one authorization attempt, and `policy_decision_id` recovers every event
that reused the *same* policy evaluation (relevant for the approval flow,
where a REQUIRE_APPROVAL attempt and its later granted retry share
`policy_decision_id` but not `decision_id`, since they are two distinct
attempts against the same policy_version+client_profile+tool+arguments).

Deliberately not an ID minted by OPA: this RI's OPA deployment does not use
bundle/decision-log infrastructure (see `PDPClient`/`compute_policy_version`),
so `policy_decision_id` is a deterministic hash over exactly the inputs the
PDP was actually given, which is sufficient to recover "which evaluation was
this" without that infrastructure.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace


def new_decision_id() -> str:
    """Unique per attempt -- never reused, even for a retried identical call."""
    return uuid.uuid4().hex


def compute_policy_decision_id(
    *, policy_version: str, client_profile: str, tool: str, arguments: dict[str, Any]
) -> str:
    digest = hashlib.sha256()
    digest.update(policy_version.encode("utf-8"))
    digest.update(client_profile.encode("utf-8"))
    digest.update(tool.encode("utf-8"))
    for key in sorted(arguments):
        digest.update(f"{key}={arguments[key]!r}".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class DecisionCorrelation:
    decision_id: str
    policy_decision_id: str
    entitlement_version: str | None
    policy_version: str | None
    mcp_request_id: str | None

    def record_on_current_span(self) -> None:
        """Expose every correlation field as an attribute on the current OTel
        span (README.md §27: "expostos no trace e no evento de auditoria") --
        the span itself is already correlated cross-process via the SDK's
        `OpenTelemetryMiddleware` (see common/otel.py); this adds the
        business-level ids the trace_id alone doesn't carry."""
        span = trace.get_current_span()
        span.set_attribute("emcp.decision_id", self.decision_id)
        span.set_attribute("emcp.policy_decision_id", self.policy_decision_id)
        if self.entitlement_version is not None:
            span.set_attribute("emcp.entitlement_version", self.entitlement_version)
        if self.policy_version is not None:
            span.set_attribute("emcp.policy_version", self.policy_version)
        if self.mcp_request_id is not None:
            span.set_attribute("emcp.mcp_request_id", self.mcp_request_id)


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    context = span.get_span_context()
    if context is None or context.trace_id == 0:
        return None
    return format(context.trace_id, "032x")
