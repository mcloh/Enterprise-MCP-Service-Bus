"""Recalculation / safe degradation (EP-11-T04, README.md §10.1, Axiom 12, P9).

When the real Gateway (EP-05) denies the `tools/call` the Agent Runtime
(EP-12) attempted for a previously-issued NBA, the Orchestrator must never
retry the same action directly against the Fabric -- that would just be the
PEP bypassed under a different name. This module's only two outcomes are:
recompute NBA over the *remaining* `filtered_offerings` (the denied action
excluded), or end the journey with an audited reason. There is no code path
here that calls a backend, the Fabric, or the Gateway -- `handle_denial`
only ever returns a new `NBADecision` or `None` for the caller (the journey
graph's `handle_denial_node`, or the Agent Runtime directly) to act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from emcp_bus.audit.events import journey_ended_after_denial, nba_recalculated
from emcp_bus.audit.sink import AuditSink
from emcp_bus.orchestrator.decision_context import DecisionContext
from emcp_bus.orchestrator.nba_model import NBADecision, NBADecisionModel


class DenialOutcome(StrEnum):
    RECALCULATED = "recalculated"
    ENDED = "ended"


@dataclass(frozen=True)
class FallbackResult:
    outcome: DenialOutcome
    nba: NBADecision | None


def handle_denial(
    context: DecisionContext,
    *,
    denied_action: str,
    decision_model: NBADecisionModel,
    audit_sink: AuditSink | None = None,
) -> FallbackResult:
    """`context.filtered_offerings` minus `denied_action`, re-run through
    `decision_model` -- never a direct call to any backend."""
    remaining = [o for o in context.filtered_offerings if o.name != denied_action]

    if not remaining:
        if audit_sink is not None:
            audit_sink.emit(
                journey_ended_after_denial(
                    subject_ref=context.profile.subject_ref, denied_action=denied_action
                )
            )
        return FallbackResult(outcome=DenialOutcome.ENDED, nba=None)

    narrowed_context = context.model_copy(update={"filtered_offerings": remaining})
    new_nba = decision_model.decide(narrowed_context)

    if audit_sink is not None:
        audit_sink.emit(
            nba_recalculated(
                subject_ref=context.profile.subject_ref,
                denied_action=denied_action,
                new_action=new_nba.action if new_nba is not None else None,
            )
        )

    if new_nba is None:
        return FallbackResult(outcome=DenialOutcome.ENDED, nba=None)
    return FallbackResult(outcome=DenialOutcome.RECALCULATED, nba=new_nba)
