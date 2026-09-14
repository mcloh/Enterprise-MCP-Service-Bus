"""DecisionContext contract (EP-11-T01)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from emcp_bus.common.models import RiskTier
from emcp_bus.orchestrator.decision_context import DecisionContext, RuntimeContext
from emcp_bus.profile_intelligence.models import ProfileView


def _profile() -> ProfileView:
    return ProfileView(
        subject_ref="subject:abc123", profile_version="v1", expires_at=datetime(2026, 1, 1)
    )


def test_decision_context_requires_entitlement_version() -> None:
    with pytest.raises(ValidationError):
        DecisionContext(  # type: ignore[call-arg]
            client_id="sales-read-agent",
            risk_ceiling=RiskTier.R1,
            allowed_tools=frozenset({"sales.customer.get"}),
            profile=_profile(),
            filtered_offerings=[],
            runtime_context=RuntimeContext(channel="app"),
        )


def test_decision_context_is_serializable_to_json() -> None:
    context = DecisionContext(
        client_id="sales-read-agent",
        entitlement_version="ent-1",
        risk_ceiling=RiskTier.R1,
        allowed_tools=frozenset({"sales.customer.get"}),
        profile=_profile(),
        filtered_offerings=[],
        runtime_context=RuntimeContext(channel="app"),
    )

    dumped = context.model_dump_json()
    restored = DecisionContext.model_validate_json(dumped)

    assert restored.entitlement_version == "ent-1"
    assert restored.allowed_tools == frozenset({"sales.customer.get"})
