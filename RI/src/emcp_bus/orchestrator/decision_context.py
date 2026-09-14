"""DecisionContext contract (EP-11-T01, README.md §1, §6.12).

Combines everything the Service Orchestrator's decisioning node (EP-11-T03)
needs into one versioned, serializable object: `ProfileView` (EP-09),
resolved MaximumEntitlement (EP-04), `FilteredOfferings` (EP-10), and
runtime context (channel/consent). Nothing downstream of this object can
widen MaximumEntitlement -- `allowed_tools`/`entitlement_version` are
carried through unchanged from EP-04's `ResolvedEntitlement`, and
`filtered_offerings` already went through EP-10's intersection; the
decisioning node only ever ranks/selects among what's already here
(Axiom 8/11).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from emcp_bus.common.models import RiskTier
from emcp_bus.profile_intelligence.models import ProfileView
from emcp_bus.registry.models import CapabilityManifest


class RuntimeContext(BaseModel):
    channel: str
    consent_purposes: frozenset[str] = frozenset()


class DecisionContext(BaseModel):
    client_id: str
    entitlement_version: str
    """Required -- a DecisionContext cannot be constructed without an
    entitlement version to correlate against (EP-11-T01 acceptance criterion)."""
    risk_ceiling: RiskTier
    allowed_tools: frozenset[str]
    profile: ProfileView
    filtered_offerings: list[CapabilityManifest]
    runtime_context: RuntimeContext
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
