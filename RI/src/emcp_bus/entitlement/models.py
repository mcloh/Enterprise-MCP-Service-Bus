"""Client profile schema (EP-04-T01, README.md §41).

A client profile is the governed object that defines a MCP Client's
`MaximumEntitlement` ceiling (§7, §17, ADR-008: granularity = domain + risk
tier). It is *not* itself the entitlement decision -- that is resolved by
the Entitlement Manager (EP-04-T02) combining this profile with the PDP's
entitlement policy (EP-03-T02). A profile only ever narrows what a client
may be granted; nothing here can widen it at runtime (Axiom 4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from emcp_bus.common.models import RiskTier


class TransactionRestrictions(BaseModel):
    """Argument/resource-level bounds enforced by the Transaction Policy (EP-03-T03).

    These are *hints* carried alongside the profile for the PDP's Rego data
    document -- the PDP, not this model, is the authority that actually
    enforces them (README.md §6.5.B, §25 Passo 2).
    """

    max_transaction_value: int | None = Field(default=None, ge=0)
    allowed_regions: list[str] | None = None
    approval_threshold: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Above this `arguments.amount`, the transaction policy returns "
            "REQUIRE_APPROVAL instead of ALLOW (README.md §26 example: "
            "payment.execute < 10k ALLOW, >= 10k REQUIRE_APPROVAL)."
        ),
    )


class CredentialPolicy(BaseModel):
    workload_identity: bool = True
    short_lived: bool = True


class AuditPolicy(BaseModel):
    level: Literal["none", "standard", "full"] = "full"


class ClientProfile(BaseModel):
    """A governed client profile (README.md §41 example)."""

    name: str = Field(description='e.g. "Sales.Read", "Finance.Payments" (README.md §7.1).')
    owner: str
    environment: Literal["dev", "ci", "production"] = "production"
    risk_ceiling: RiskTier
    allowed_tools: list[str] = Field(
        min_length=1,
        description="Canonical <domain>.<capability> tool names (README.md §39).",
    )
    restrictions: TransactionRestrictions = Field(default_factory=TransactionRestrictions)
    credential_policy: CredentialPolicy = Field(default_factory=CredentialPolicy)
    audit: AuditPolicy = Field(default_factory=AuditPolicy)

    @field_validator("name")
    @classmethod
    def _name_is_domain_dot_qualifier(cls, value: str) -> str:
        if "." not in value:
            raise ValueError(
                f"client profile name {value!r} must be '<Domain>.<Qualifier>' "
                "(e.g. 'Sales.Read') per README.md §7.1/§39"
            )
        return value

    @field_validator("allowed_tools")
    @classmethod
    def _tools_are_domain_dot_capability(cls, tools: list[str]) -> list[str]:
        for tool in tools:
            if "." not in tool:
                raise ValueError(
                    f"tool name {tool!r} must be '<domain>.<capability>' per README.md §39"
                )
        return tools
