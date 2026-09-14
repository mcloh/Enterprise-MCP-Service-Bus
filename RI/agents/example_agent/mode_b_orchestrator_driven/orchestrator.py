"""Modo B -- Service Orchestrator como unico cerebro de NBA/NBO (EP-13-T06,
`could`, ADR-024, README.md §6.12).

Contrast with `emcp_bus.agent_runtime.global_supervisor` (Modo A, EP-13-T05):
there, an external Global Supervisor decides routing and our Orchestrator
never participates. Here, our own Orchestrator -- the real journey
`StateGraph` (EP-11-T02), invoked once per relevant MCP Client for the same
subject -- is the *only* thing that ever decides which backend acts; no
external Global Supervisor is consulted at all. Each backend/agent still
remains its own MCP Client with its own entitlement ceiling (ADR-008); this
class only combines what each of them is independently allowed to offer.

Deliberately does **not** extend `emcp_bus.orchestrator.graph.JourneyState`/
`build_journey_graph` to natively span multiple `client_id`s in one run --
that graph is already real, tested, and used unmodified per client_id here
(`README.md §6.12`'s fixed backbone: `resolve_profile -> resolve_entitlement
-> filter_offerings -> decide_nba -> approval_gate`); the *combining* step
across clients lives in this module instead, one layer above the graph,
exactly where `AgentDispatcher`'s own docstring already says post-decision
orchestration belongs ("one layer up"). A native multi-client journey graph
is a natural, larger future extension of EP-11-T02 -- not attempted here to
avoid risking an already-tested core component for a `could`-priority demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from emcp_bus.agent_runtime.dispatcher import AgentDispatcher, DispatchResult
from emcp_bus.orchestrator.nba_model import NBADecision


@dataclass(frozen=True)
class ModeBDecision:
    chosen: NBADecision
    considered: list[NBADecision]


class ModeBOrchestrator:
    def __init__(
        self,
        *,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        dispatcher: AgentDispatcher,
        client_ids: list[str],
    ) -> None:
        self._graph = graph
        self._dispatcher = dispatcher
        self._client_ids = client_ids

    def decide(self, *, subject_id: str, channel: str) -> ModeBDecision | None:
        """Invokes the real journey graph once per `client_ids` entry --
        each run independently resolves that client's own profile/
        entitlement/offerings (EP-11-T02's existing, unmodified nodes) --
        then combines the resulting `NBADecision`s. A `client_id` whose
        journey ends without a survivable offering (`nba is None`) simply
        contributes nothing to `considered`, never an error."""
        candidates: list[NBADecision] = []
        for client_id in self._client_ids:
            config: RunnableConfig = {
                "configurable": {"thread_id": f"mode-b-{subject_id}-{client_id}"}
            }
            result = self._graph.invoke(
                {"client_id": client_id, "raw_subject_id": subject_id, "channel": channel}, config
            )
            nba = result.get("nba")
            if nba is not None:
                candidates.append(nba)

        chosen = self._combine(candidates)
        if chosen is None:
            return None
        return ModeBDecision(chosen=chosen, considered=candidates)

    async def decide_and_dispatch(
        self, *, subject_id: str, channel: str, arguments: dict[str, Any] | None = None
    ) -> DispatchResult | None:
        """Decides, then dispatches `chosen` through the real
        `AgentDispatcher` (EP-12-T01) -- the Agent Runtime "apenas despacha
        o resultado" (EP-13-T06's own acceptance criterion): this method
        adds no authorization logic of its own, `dispatcher.dispatch` goes
        through the exact same Gateway/PDP reauthorization any other
        dispatch does."""
        decision = self.decide(subject_id=subject_id, channel=channel)
        if decision is None:
            return None
        return await self._dispatcher.dispatch(decision.chosen, arguments=arguments or {})

    @staticmethod
    def _combine(candidates: list[NBADecision]) -> NBADecision | None:
        """Reference combining rule (not a claim of optimality -- matching
        `RuleBasedNBADecisionModel`'s own stance, EP-11-T03): a pending
        Finance obligation always outranks a discretionary Sales offer for
        the same subject, when both exist. A real deployment would plug in
        whatever cross-domain ranking model it actually has (EP-11-T03's
        pluggable `NBADecisionModel` interface, applied one level up)."""
        if not candidates:
            return None
        finance_candidates = [c for c in candidates if c.action.startswith("finance.")]
        return finance_candidates[0] if finance_candidates else candidates[0]
