"""Journey StateGraph (EP-11-T02, README.md §6.12).

Fixed corporate-standard nodes (`docs/research/hoshikawa-agent-platform-oci.md`'s
pattern: dev only adds domain nodes, never touches the backbone):

    resolve_profile -> resolve_entitlement -> filter_offerings -> decide_nba
        -> approval_gate (EP-11-T05, may pause the graph) -> END

Plus a second entry path for the denial-recalculation loop (EP-11-T04):
re-invoking the graph with `denied_action` set routes straight to
`handle_denial_node` (skipping profile/entitlement/offering resolution,
which haven't changed) -> `decide_nba` again over the narrowed offerings ->
`approval_gate` -> END, or straight to END if no offering remains.

Checkpointing (this task's other acceptance criterion): pass any LangGraph
`Checkpointer` (`langgraph.checkpoint.sqlite.SqliteSaver` in dev, per
ADR-022's plugable-provider pattern -- a `postgres`/`mongodb` one is a
drop-in swap in production, no graph code changes). A real IdP-integrated
deployment resumes a paused `approval_gate` by calling
`graph.invoke(Command(resume="approved"), config)` once
`emcp_bus.approval.service.ApprovalService.grant()` reports the matching
approval as granted (EP-11-T05's docstring) -- wiring that callback is a
thin adapter, not shown here since it depends on how a deployment surfaces
approvals (CLI, API, ApprovalService callback), not on this graph's shape.
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from emcp_bus.audit.sink import AuditSink
from emcp_bus.common.models import RiskTier
from emcp_bus.entitlement.manager import EntitlementManager
from emcp_bus.offering_filter.service import ConsentContext, OfferingFilterService
from emcp_bus.orchestrator.decision_context import DecisionContext, RuntimeContext
from emcp_bus.orchestrator.fallback import handle_denial
from emcp_bus.orchestrator.hitl_node import approval_gate_node, requires_approval
from emcp_bus.orchestrator.nba_model import NBADecisionModel
from emcp_bus.orchestrator.state import JourneyState
from emcp_bus.profile_intelligence.rule_based_provider import ProfileIntelligenceProvider


def _decision_context_from_state(
    state: JourneyState, *, exclude: frozenset[str] = frozenset()
) -> DecisionContext:
    offerings = [o for o in state["filtered_offerings"] if o.name not in exclude]
    return DecisionContext(
        client_id=state["client_id"],
        entitlement_version=state["entitlement_version"],
        risk_ceiling=RiskTier(state["risk_ceiling"]),
        allowed_tools=frozenset(state["allowed_tools"]),
        profile=state["profile"],
        filtered_offerings=offerings,
        runtime_context=RuntimeContext(channel=state["channel"]),
    )


def build_journey_graph(
    *,
    profile_provider: ProfileIntelligenceProvider,
    entitlement_manager: EntitlementManager,
    offering_filter: OfferingFilterService,
    decision_model: NBADecisionModel,
    checkpointer: Any,
    audit_sink: AuditSink | None = None,
    consent_context: ConsentContext | None = None,
) -> CompiledStateGraph[JourneyState, None, JourneyState, JourneyState]:
    consent_context = consent_context or ConsentContext()

    def resolve_profile_node(state: JourneyState) -> dict[str, Any]:
        profile = profile_provider.resolve(state["raw_subject_id"])
        return {"profile": profile}

    def resolve_entitlement_node(state: JourneyState) -> dict[str, Any]:
        resolved = entitlement_manager.resolve(state["client_id"])
        return {
            "allowed_tools": sorted(resolved.allowed_tools),
            "entitlement_version": resolved.entitlement_version,
            "risk_ceiling": resolved.risk_ceiling.value,
        }

    def filter_offerings_node(state: JourneyState) -> dict[str, Any]:
        offerings = offering_filter.filtered_offerings(
            allowed_tools=frozenset(state["allowed_tools"]), context=consent_context
        )
        return {"filtered_offerings": offerings}

    def decide_nba_node(state: JourneyState) -> dict[str, Any]:
        excluded = frozenset(state.get("excluded_actions", []))
        context = _decision_context_from_state(state, exclude=excluded)
        nba = decision_model.decide(context)
        needs_approval = nba is not None and requires_approval(
            context.filtered_offerings, nba.action
        )
        return {"nba": nba, "nba_requires_approval": needs_approval}

    def handle_denial_node(state: JourneyState) -> dict[str, Any]:
        denied_action = state["denied_action"]
        assert denied_action is not None
        already_excluded = frozenset(state.get("excluded_actions", []))
        context = _decision_context_from_state(state, exclude=already_excluded)
        result = handle_denial(
            context,
            denied_action=denied_action,
            decision_model=decision_model,
            audit_sink=audit_sink,
        )
        needs_approval = result.nba is not None and requires_approval(
            context.filtered_offerings, result.nba.action
        )
        return {
            "nba": result.nba,
            "nba_requires_approval": needs_approval,
            "excluded_actions": [*already_excluded, denied_action],
            "denial_outcome": result.outcome.value,
            "denied_action": None,
        }

    def route_entry(state: JourneyState) -> Literal["fresh", "denial_reentry"]:
        return "denial_reentry" if state.get("denied_action") else "fresh"

    def route_after_denial(state: JourneyState) -> str:
        return "approval_gate" if state.get("nba") is not None else END

    builder: StateGraph[JourneyState, None, JourneyState, JourneyState] = StateGraph(JourneyState)
    builder.add_node("resolve_profile", resolve_profile_node)
    builder.add_node("resolve_entitlement", resolve_entitlement_node)
    builder.add_node("filter_offerings", filter_offerings_node)
    builder.add_node("decide_nba", decide_nba_node)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("handle_denial", handle_denial_node)

    builder.add_conditional_edges(
        START, route_entry, {"fresh": "resolve_profile", "denial_reentry": "handle_denial"}
    )
    builder.add_edge("resolve_profile", "resolve_entitlement")
    builder.add_edge("resolve_entitlement", "filter_offerings")
    builder.add_edge("filter_offerings", "decide_nba")
    builder.add_edge("decide_nba", "approval_gate")
    builder.add_conditional_edges(
        "handle_denial", route_after_denial, {"approval_gate": "approval_gate", END: END}
    )
    builder.add_edge("approval_gate", END)

    return builder.compile(checkpointer=checkpointer)
