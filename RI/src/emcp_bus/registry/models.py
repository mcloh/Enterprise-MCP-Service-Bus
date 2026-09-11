"""Capability manifest schema (EP-02-T01, README.md §6.8, §23, §39, §40).

Reconciles the two illustrative shapes in README.md: the publishing-pipeline
manifest example (§6.8, camelCase, `riskTier: medium`) and the Tool Registry
metadata example (§23, snake_case, `risk_tier: R2`). This RI standardizes on
the §23 field names and the `RiskTier` R0-R4 enum, because that is the same
enum a `ClientProfile.risk_ceiling` uses (EP-04-T01) -- one risk vocabulary,
not two, is what lets entitlement resolution compare a tool's risk against a
client's ceiling directly (see `emcp_bus.common.models.risk_tier_at_or_below`).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from emcp_bus.common.models import RiskTier


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class LifecycleStatus(StrEnum):
    """Registry governance lifecycle (README.md §23)."""

    NOMINATE = "nominate"
    REVIEW = "review"
    REGISTER = "register"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class BackendRef(BaseModel):
    """Where the Fabric (EP-06-T01) routes a capability once authorized."""

    type: Literal["rest", "mcp", "grpc"] = "mcp"
    service: str = Field(
        description="Adapter/service id the Fabric router resolves, e.g. 'sales-domain'."
    )
    operation: str | None = Field(
        default=None, description="Informational, e.g. 'GET /v2/customers/{id}' (README.md §6.8)."
    )


class ApprovalPolicy(BaseModel):
    required: bool = False


class ObservabilityPolicy(BaseModel):
    audit_level: Literal["none", "standard", "full"] = "full"


class LifecycleInfo(BaseModel):
    status: LifecycleStatus = LifecycleStatus.NOMINATE
    sunset_after: date | None = None


class CapabilityManifest(BaseModel):
    name: str = Field(description="Canonical '<domain>.<capability>' name (README.md §39).")
    version: str = Field(description="SemVer, e.g. '1.2.0' (README.md §40).")
    domain: str
    owner: str
    risk_tier: RiskTier
    side_effects: bool
    idempotent: bool
    data_classification: list[DataClassification] = Field(
        default_factory=lambda: [DataClassification.INTERNAL]
    )
    entitlements: list[str] = Field(
        min_length=1,
        description="ClientProfile names required to see/call this capability (EP-04).",
    )
    backend: BackendRef
    approval: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    observability: ObservabilityPolicy = Field(default_factory=ObservabilityPolicy)
    lifecycle: LifecycleInfo = Field(default_factory=LifecycleInfo)

    @field_validator("name")
    @classmethod
    def _name_is_canonical(cls, value: str) -> str:
        if "." not in value:
            raise ValueError(
                f"capability name {value!r} must be '<domain>.<capability>' (README.md §39)"
            )
        return value

    @field_validator("domain")
    @classmethod
    def _domain_matches_name_prefix(cls, value: str, info: ValidationInfo) -> str:
        name = info.data.get("name")
        if isinstance(name, str) and not name.startswith(f"{value}."):
            raise ValueError(
                f"domain {value!r} does not match the prefix of name {name!r} "
                "(README.md §39: name must be '<domain>.<capability>')"
            )
        return value
