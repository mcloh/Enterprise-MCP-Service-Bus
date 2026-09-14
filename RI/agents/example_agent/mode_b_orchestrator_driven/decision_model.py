"""Reference `NBADecisionModel` for Modo B (EP-13-T06, `could`, ADR-024).

Same least-risk-tier-first selection rule as
`emcp_bus.orchestrator.decisioning.RuleBasedNBADecisionModel` (EP-11-T03) --
not a claim of optimality, just a simple, legible priority rule (see that
module's own docstring). The one deliberate difference: `agent` here is
always `context.client_id`, the real MCP Client whose entitlement produced
`context.filtered_offerings` in the first place -- never a separate label
from some mapping table. `AgentDispatcher` (EP-12-T01) resolves a credential
*for* `nba.agent` via `AgentTokenProvider.token_for`, and the only
credential this Orchestrator may ever dispatch a given offering with is the
one belonging to the client whose entitlement actually authorized it (Axiom
4/9) -- keeping `agent == client_id` makes that self-evidently true, with
no separate table that could drift out of sync with which client resolved
which offerings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from emcp_bus.orchestrator.decision_context import DecisionContext
from emcp_bus.orchestrator.decisioning import DEFAULT_TTL
from emcp_bus.orchestrator.nba_model import NBADecision


class DomainRoutingNBADecisionModel:
    def decide(self, context: DecisionContext) -> NBADecision | None:
        if not context.filtered_offerings:
            return None

        offering = min(context.filtered_offerings, key=lambda m: (m.risk_tier.value, m.name))
        reason_codes = ["ELIGIBLE", *context.profile.reason_codes]

        return NBADecision(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            action=offering.name,
            capability_version=offering.version,
            subject_ref=context.profile.subject_ref,
            channel=context.runtime_context.channel,
            agent=context.client_id,
            reason_codes=reason_codes,
            policy_context={
                "entitlementVersion": context.entitlement_version,
                "consentPurposes": sorted(context.runtime_context.consent_purposes),
            },
            expires_at=datetime.now(UTC) + DEFAULT_TTL,
        )
