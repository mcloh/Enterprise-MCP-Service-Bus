"""Sanity checks for the M1 config schemas (EP-01-T02, EP-02-T01, EP-04-T01)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from emcp_bus.common.models import RiskTier, risk_tier_at_or_below
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.registry.models import BackendRef, CapabilityManifest


def test_risk_tier_ordering() -> None:
    assert risk_tier_at_or_below(RiskTier.R1, RiskTier.R2)
    assert not risk_tier_at_or_below(RiskTier.R3, RiskTier.R2)
    assert risk_tier_at_or_below(RiskTier.R0, RiskTier.R0)


def test_client_profile_from_readme_example() -> None:
    profile = ClientProfile.model_validate(
        {
            "name": "Sales.Write",
            "owner": "sales-platform",
            "environment": "production",
            "risk_ceiling": "R2",
            "allowed_tools": [
                "sales.customer.get",
                "sales.order.get",
                "sales.quote.create",
                "sales.quote.update",
            ],
            "restrictions": {"max_transaction_value": 500000},
            "credential_policy": {"workload_identity": True, "short_lived": True},
            "audit": {"level": "full"},
        }
    )
    assert profile.risk_ceiling is RiskTier.R2
    assert "sales.quote.create" in profile.allowed_tools


def test_client_profile_rejects_flat_name() -> None:
    with pytest.raises(ValidationError):
        ClientProfile.model_validate(
            {
                "name": "SalesWrite",  # missing "<Domain>.<Qualifier>"
                "owner": "sales-platform",
                "risk_ceiling": "R2",
                "allowed_tools": ["sales.quote.create"],
            }
        )


def test_client_registration_references_a_profile_by_name() -> None:
    registration = ClientRegistration.model_validate(
        {"client_id": "sales-write-agent", "profile": "Sales.Write"}
    )
    assert registration.profile == "Sales.Write"


def test_capability_manifest_domain_must_prefix_name() -> None:
    manifest = CapabilityManifest.model_validate(
        {
            "name": "sales.quote.create",
            "version": "2.1.0",
            "domain": "sales",
            "owner": "sales-platform",
            "risk_tier": "R2",
            "side_effects": True,
            "idempotent": False,
            "entitlements": ["Sales.Write", "Sales.Approve"],
            "backend": {"type": "mcp", "service": "sales-domain"},
        }
    )
    assert manifest.backend == BackendRef(type="mcp", service="sales-domain")

    with pytest.raises(ValidationError):
        CapabilityManifest.model_validate(
            {
                "name": "sales.quote.create",
                "version": "2.1.0",
                "domain": "finance",  # mismatched prefix
                "owner": "sales-platform",
                "risk_tier": "R2",
                "side_effects": True,
                "idempotent": False,
                "entitlements": ["Sales.Write"],
                "backend": {"type": "mcp", "service": "sales-domain"},
            }
        )
