"""Reference `NBADecisionModel` (EP-11-T03): deterministic rules/priority
over `DecisionContext.filtered_offerings` -- not an AI model, not
clustering. See `nba_model.py`'s module docstring for the pluggable
interface a real ranking model would implement instead, and
`RI/docs/Assumptions.md` for why this RI doesn't attempt "real" ranking without
a real dataset.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from emcp_bus.orchestrator.decision_context import DecisionContext
from emcp_bus.orchestrator.nba_model import NBADecision

DEFAULT_AGENT = "engagement-assistant"
DEFAULT_TTL = timedelta(hours=1)


class RuleBasedNBADecisionModel:
    """Picks the lowest-risk-tier offering (least friction first), tie-broken
    by name for determinism -- a simple, legible priority rule, not a claim
    of optimality. `reason_codes` always includes `ELIGIBLE` plus whatever
    `ProfileView.reason_codes` the profile carried (README.md §6.13 example:
    `["ELIGIBLE", "ACTIVATION_OBJECTIVE", "FREQUENCY_OK"]`)."""

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
            agent=DEFAULT_AGENT,
            reason_codes=reason_codes,
            policy_context={
                "entitlementVersion": context.entitlement_version,
                "consentPurposes": sorted(context.runtime_context.consent_purposes),
            },
            expires_at=datetime.now(UTC) + DEFAULT_TTL,
        )
