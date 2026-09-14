"""Recalculation / safe degradation (EP-11-T04, README.md §10.1, Axiom 12, P9)."""

from __future__ import annotations

from datetime import datetime

from emcp_bus.audit.sink import InMemoryAuditSink
from emcp_bus.common.models import RiskTier
from emcp_bus.orchestrator.decision_context import DecisionContext, RuntimeContext
from emcp_bus.orchestrator.decisioning import RuleBasedNBADecisionModel
from emcp_bus.orchestrator.fallback import DenialOutcome, handle_denial
from emcp_bus.profile_intelligence.models import ProfileView
from emcp_bus.registry.models import (
    ApprovalPolicy,
    BackendRef,
    CapabilityManifest,
    LifecycleInfo,
    LifecycleStatus,
)


def _manifest(name: str) -> CapabilityManifest:
    return CapabilityManifest(
        name=name,
        version="1.0.0",
        domain=name.split(".", 1)[0],
        owner="sales-team",
        risk_tier=RiskTier.R1,
        side_effects=False,
        idempotent=True,
        entitlements=["Sales.Read"],
        backend=BackendRef(type="mcp", service="sales-domain"),
        approval=ApprovalPolicy(),
        lifecycle=LifecycleInfo(status=LifecycleStatus.ACTIVE),
    )


def _context(offerings: list[CapabilityManifest]) -> DecisionContext:
    profile = ProfileView(
        subject_ref="subject:abc123", profile_version="v1", expires_at=datetime(2026, 1, 1)
    )
    return DecisionContext(
        client_id="sales-read-agent",
        entitlement_version="ent-1",
        risk_ceiling=RiskTier.R2,
        allowed_tools=frozenset(m.name for m in offerings),
        profile=profile,
        filtered_offerings=offerings,
        runtime_context=RuntimeContext(channel="app"),
    )


def test_handle_denial_recalculates_over_the_remaining_offerings() -> None:
    context = _context([_manifest("sales.customer.get"), _manifest("sales.order.get")])

    result = handle_denial(
        context, denied_action="sales.customer.get", decision_model=RuleBasedNBADecisionModel()
    )

    assert result.outcome is DenialOutcome.RECALCULATED
    assert result.nba is not None
    assert result.nba.action == "sales.order.get"


def test_handle_denial_ends_the_journey_when_no_offering_remains() -> None:
    context = _context([_manifest("sales.customer.get")])

    result = handle_denial(
        context, denied_action="sales.customer.get", decision_model=RuleBasedNBADecisionModel()
    )

    assert result.outcome is DenialOutcome.ENDED
    assert result.nba is None


def test_handle_denial_never_reselects_the_denied_action() -> None:
    context = _context([_manifest("sales.customer.get"), _manifest("sales.order.get")])

    result = handle_denial(
        context, denied_action="sales.customer.get", decision_model=RuleBasedNBADecisionModel()
    )

    assert result.nba is not None
    assert result.nba.action != "sales.customer.get"


def test_handle_denial_emits_an_audited_event_on_recalculation() -> None:
    sink = InMemoryAuditSink()
    context = _context([_manifest("sales.customer.get"), _manifest("sales.order.get")])

    handle_denial(
        context,
        denied_action="sales.customer.get",
        decision_model=RuleBasedNBADecisionModel(),
        audit_sink=sink,
    )

    assert len(sink.events) == 1
    assert sink.events[0].event_type == "nba_recalculated"


def test_handle_denial_emits_an_audited_event_on_ending() -> None:
    sink = InMemoryAuditSink()
    context = _context([_manifest("sales.customer.get")])

    handle_denial(
        context,
        denied_action="sales.customer.get",
        decision_model=RuleBasedNBADecisionModel(),
        audit_sink=sink,
    )

    assert len(sink.events) == 1
    assert sink.events[0].event_type == "journey_ended_after_denial"
