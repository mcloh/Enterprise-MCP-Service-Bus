"""Audit event taxonomy (EP-08-T02, README.md §27).

One factory function per event type named in §27's taxonomy (plus the
bypass-detection event from EP-05-T07). Each hard-codes its `EventCategory`
so callers never have to decide IC/NOC/GRL per call site -- that
classification is a property of the event type itself, not of the moment
it fires.
"""

from __future__ import annotations

from typing import Any

from emcp_bus.audit.correlation import DecisionCorrelation, current_trace_id
from emcp_bus.audit.models import EventCategory, EventEnvelope


def _base(
    *,
    event_type: str,
    category: EventCategory,
    client_id: str | None = None,
    profile_name: str | None = None,
    tool: str | None = None,
    reason_code: str | None = None,
    correlation: DecisionCorrelation | None = None,
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        category=category,
        client_id=client_id,
        profile_name=profile_name,
        tool=tool,
        reason_code=reason_code,
        decision_id=correlation.decision_id if correlation else None,
        policy_decision_id=correlation.policy_decision_id if correlation else None,
        entitlement_version=correlation.entitlement_version if correlation else None,
        policy_version=correlation.policy_version if correlation else None,
        mcp_request_id=correlation.mcp_request_id if correlation else None,
        trace_id=current_trace_id(),
        payload=payload or {},
    )


def client_authenticated(*, client_id: str, mcp_request_id: str | None) -> EventEnvelope:
    return _base(
        event_type="client_authenticated",
        category=EventCategory.IC,
        client_id=client_id,
        payload={"mcp_request_id": mcp_request_id},
    )


def tools_list_filtered(
    *, client_id: str, profile_name: str, entitlement_version: str, allowed: int, total: int
) -> EventEnvelope:
    return _base(
        event_type="tools_list_filtered",
        category=EventCategory.GRL,
        client_id=client_id,
        profile_name=profile_name,
        payload={"entitlement_version": entitlement_version, "allowed": allowed, "total": total},
    )


def tool_call_allowed(
    *, client_id: str, profile_name: str, tool: str, correlation: DecisionCorrelation
) -> EventEnvelope:
    return _base(
        event_type="tool_call_allowed",
        category=EventCategory.IC,
        client_id=client_id,
        profile_name=profile_name,
        tool=tool,
        correlation=correlation,
    )


def tool_call_denied(
    *,
    client_id: str | None,
    profile_name: str | None,
    tool: str | None,
    reason_code: str,
    correlation: DecisionCorrelation | None = None,
) -> EventEnvelope:
    return _base(
        event_type="tool_call_denied",
        category=EventCategory.GRL,
        client_id=client_id,
        profile_name=profile_name,
        tool=tool,
        reason_code=reason_code,
        correlation=correlation,
    )


def tool_call_require_approval(
    *,
    client_id: str,
    profile_name: str,
    tool: str,
    approval_id: str,
    correlation: DecisionCorrelation,
) -> EventEnvelope:
    return _base(
        event_type="tool_call_require_approval",
        category=EventCategory.GRL,
        client_id=client_id,
        profile_name=profile_name,
        tool=tool,
        correlation=correlation,
        payload={"approval_id": approval_id},
    )


def approval_granted(*, approval_id: str, client_profile: str, tool: str) -> EventEnvelope:
    return _base(
        event_type="approval_granted",
        category=EventCategory.GRL,
        profile_name=client_profile,
        tool=tool,
        payload={"approval_id": approval_id},
    )


def pdp_unavailable(*, client_id: str, tool: str) -> EventEnvelope:
    return _base(
        event_type="pdp_unavailable",
        category=EventCategory.NOC,
        client_id=client_id,
        tool=tool,
    )


def backend_credential_unavailable(*, client_id: str, tool: str, backend: str) -> EventEnvelope:
    return _base(
        event_type="backend_credential_unavailable",
        category=EventCategory.NOC,
        client_id=client_id,
        tool=tool,
        payload={"backend": backend},
    )


def bypass_attempt_detected(*, backend: str, reason: str) -> EventEnvelope:
    """EP-05-T07: a request reached a domain server without the Gateway's
    outbound credential -- i.e. it did not traverse the PEP."""
    return _base(
        event_type="bypass_attempt_detected",
        category=EventCategory.GRL,
        payload={"backend": backend, "reason": reason},
    )


def nba_recalculated(
    *, subject_ref: str, denied_action: str, new_action: str | None
) -> EventEnvelope:
    """EP-11-T04: the Orchestrator recomputed NBA after a Gateway DENY,
    never retried the denied action directly against the Fabric."""
    return _base(
        event_type="nba_recalculated",
        category=EventCategory.IC,
        payload={
            "subject_ref": subject_ref,
            "denied_action": denied_action,
            "new_action": new_action,
        },
    )


def agent_turn_completed(
    *, agent: str, tools_attempted: list[str], tools_denied: list[str]
) -> EventEnvelope:
    """EP-13-T01: one business-journey event per agent turn (ADR-022's
    hybrid instrumentation -- an automatic OTel span per turn already exists
    via common/otel.py; this is the manual, fail-open business event on
    top). `tools_denied` is never proof of a bug -- the Gateway/PDP denying
    a tool the agent (or a prompt trying to manipulate it) attempted is the
    security boundary working as intended (README.md §29, Teste 3 of §45)."""
    return _base(
        event_type="agent_turn_completed",
        category=EventCategory.IC,
        client_id=agent,
        payload={"tools_attempted": tools_attempted, "tools_denied": tools_denied},
    )


def journey_ended_after_denial(*, subject_ref: str, denied_action: str) -> EventEnvelope:
    """EP-11-T04: no remaining offering survived a Gateway DENY -- the
    journey ends here, audited, rather than the Orchestrator attempting any
    direct Fabric call (README.md §10.1, Axiom 12, P9)."""
    return _base(
        event_type="journey_ended_after_denial",
        category=EventCategory.GRL,
        payload={"subject_ref": subject_ref, "denied_action": denied_action},
    )
