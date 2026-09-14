"""Human-in-the-loop gate (EP-11-T05). The actual pause/resume behavior is
covered end to end through the real graph in test_orchestrator_graph.py;
this file covers `approval_gate_node`'s two branches that never interrupt.
"""

from __future__ import annotations

from datetime import datetime

from emcp_bus.common.models import RiskTier
from emcp_bus.orchestrator.hitl_node import approval_gate_node, requires_approval
from emcp_bus.orchestrator.nba_model import NBADecision
from emcp_bus.registry.models import (
    ApprovalPolicy,
    BackendRef,
    CapabilityManifest,
    LifecycleInfo,
    LifecycleStatus,
)


def _manifest(name: str, *, approval_required: bool) -> CapabilityManifest:
    return CapabilityManifest(
        name=name,
        version="1.0.0",
        domain=name.split(".", 1)[0],
        owner="finance-team",
        risk_tier=RiskTier.R3 if approval_required else RiskTier.R1,
        side_effects=True,
        idempotent=False,
        entitlements=["Finance.Payments"],
        backend=BackendRef(type="mcp", service="finance-domain"),
        approval=ApprovalPolicy(required=approval_required),
        lifecycle=LifecycleInfo(status=LifecycleStatus.ACTIVE),
    )


def test_requires_approval_true_for_a_flagged_capability() -> None:
    offerings = [_manifest("finance.payment.execute", approval_required=True)]

    assert requires_approval(offerings, "finance.payment.execute") is True


def test_requires_approval_false_for_an_unflagged_capability() -> None:
    offerings = [_manifest("sales.customer.get", approval_required=False)]

    assert requires_approval(offerings, "sales.customer.get") is False


def test_approval_gate_node_skips_when_there_is_no_nba() -> None:
    result = approval_gate_node({"nba": None})

    assert result == {"approval_status": "not_applicable"}


def test_approval_gate_node_skips_when_approval_is_not_required() -> None:
    nba = NBADecision(
        decision_id="dec-1",
        action="sales.customer.get",
        capability_version="1.0.0",
        subject_ref="subject:abc123",
        channel="app",
        agent="engagement-assistant",
        reason_codes=["ELIGIBLE"],
        policy_context={},
        expires_at=datetime(2026, 1, 1),
    )
    result = approval_gate_node({"nba": nba, "nba_requires_approval": False})

    assert result == {"approval_status": "not_required"}
