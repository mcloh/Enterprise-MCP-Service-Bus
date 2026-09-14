"""NBA/NBO contract + pluggable decision interface (EP-11-T03, README.md
§6.13, ADR-024).

Field names/shape mirror README.md §6.13's dispatch example exactly
(`decisionId`, `action`, `capabilityVersion`, `subjectRef`, `channel`,
`agent`, `reasonCodes`, `policyContext`, `expiresAt`).

`NBADecisionModel` is a `Protocol` on purpose (ADR-024, EP-11-T03 acceptance
criterion): swapping the reference rule-based implementation
(`decisioning.RuleBasedNBADecisionModel`) for an AI ranking/recommendation
model changes nothing about `DecisionContext` in or `NBADecision` out, and
therefore nothing about EP-03/EP-04/EP-05's authorization surface -- the
model only ever ranks/selects among `DecisionContext.filtered_offerings`,
already intersected with MaximumEntitlement by EP-10 before this code ever
sees it (Axiom 8/11).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from emcp_bus.orchestrator.decision_context import DecisionContext


class NBADecision(BaseModel):
    decision_id: str
    action: str
    capability_version: str
    subject_ref: str
    channel: str
    agent: str
    reason_codes: list[str]
    policy_context: dict[str, Any]
    expires_at: datetime


class NBADecisionModel(Protocol):
    def decide(self, context: DecisionContext) -> NBADecision | None:
        """`None` when no offering survives `context.filtered_offerings` --
        the caller (the journey graph, EP-11-T02) must treat this as "end
        the journey," never as an excuse to look outside `filtered_offerings`."""
        ...
