"""Reference NBADecisionModel (EP-11-T03, README.md §6.13)."""

from __future__ import annotations

from datetime import datetime

from emcp_bus.common.models import RiskTier
from emcp_bus.orchestrator.decision_context import DecisionContext, RuntimeContext
from emcp_bus.orchestrator.decisioning import RuleBasedNBADecisionModel
from emcp_bus.orchestrator.nba_model import NBADecision, NBADecisionModel
from emcp_bus.profile_intelligence.models import ProfileView
from emcp_bus.registry.models import (
    ApprovalPolicy,
    BackendRef,
    CapabilityManifest,
    LifecycleInfo,
    LifecycleStatus,
)


def _manifest(name: str, risk_tier: RiskTier = RiskTier.R1) -> CapabilityManifest:
    return CapabilityManifest(
        name=name,
        version="1.0.0",
        domain=name.split(".", 1)[0],
        owner="sales-team",
        risk_tier=risk_tier,
        side_effects=False,
        idempotent=True,
        entitlements=["Sales.Read"],
        backend=BackendRef(type="mcp", service="sales-domain"),
        approval=ApprovalPolicy(),
        lifecycle=LifecycleInfo(status=LifecycleStatus.ACTIVE),
    )


def _context(offerings: list[CapabilityManifest]) -> DecisionContext:
    profile = ProfileView(
        subject_ref="subject:abc123",
        profile_version="v1",
        reason_codes=["LOW_RECENCY"],
        expires_at=datetime(2026, 1, 1),
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


def test_decide_returns_none_when_no_offerings_survive() -> None:
    model = RuleBasedNBADecisionModel()

    assert model.decide(_context([])) is None


def test_decide_always_includes_reason_codes_policy_context_and_expiry() -> None:
    """EP-11-T03 acceptance criterion: every NBA/NBO carries reasonCodes,
    policyContext and expiresAt (README.md §6.13)."""
    model = RuleBasedNBADecisionModel()
    context = _context([_manifest("sales.customer.get")])

    nba = model.decide(context)

    assert nba is not None
    assert "ELIGIBLE" in nba.reason_codes
    assert "LOW_RECENCY" in nba.reason_codes
    assert nba.policy_context["entitlementVersion"] == "ent-1"
    assert nba.expires_at is not None


def test_decide_prefers_the_lowest_risk_tier_offering() -> None:
    model = RuleBasedNBADecisionModel()
    context = _context(
        [_manifest("sales.quote.create", RiskTier.R2), _manifest("sales.customer.get", RiskTier.R1)]
    )

    nba = model.decide(context)

    assert nba is not None
    assert nba.action == "sales.customer.get"


def test_decide_never_selects_an_offering_outside_filtered_offerings() -> None:
    """The structural guarantee EP-11-T03's second acceptance criterion
    relies on: the model only ever ranks what DecisionContext already
    carries -- there is no code path here that looks anywhere else."""
    model = RuleBasedNBADecisionModel()
    context = _context([_manifest("sales.customer.get")])

    nba = model.decide(context)

    assert nba is not None
    assert nba.action in {o.name for o in context.filtered_offerings}


def test_a_swapped_decision_model_satisfies_the_same_protocol() -> None:
    """EP-11-T03's pluggability criterion: any NBADecisionModel
    implementation works with the exact same DecisionContext/NBADecision
    contract -- no EP-03/EP-04/EP-05 change required to swap one in."""

    class AlwaysFirstOfferingModel:
        def decide(self, context: DecisionContext) -> NBADecision | None:
            if not context.filtered_offerings:
                return None
            offering = context.filtered_offerings[0]
            return NBADecision(
                decision_id="dec-fixed",
                action=offering.name,
                capability_version=offering.version,
                subject_ref=context.profile.subject_ref,
                channel=context.runtime_context.channel,
                agent="test-agent",
                reason_codes=["ELIGIBLE"],
                policy_context={"entitlementVersion": context.entitlement_version},
                expires_at=datetime(2026, 1, 1),
            )

    model: NBADecisionModel = AlwaysFirstOfferingModel()
    context = _context([_manifest("sales.customer.get")])

    nba = model.decide(context)

    assert nba is not None
    assert nba.action == "sales.customer.get"
