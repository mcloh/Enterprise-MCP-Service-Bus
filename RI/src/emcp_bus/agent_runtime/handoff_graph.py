"""Agent-to-agent handoff (EP-12-T03, `could`, README.md §6.13, ADR-022, ADR-023).

Two concerns, kept structurally separate on purpose:

1. **Context minimization** (`build_handoff_payload`): the destination agent
   receives only an explicitly declared subset of the journey's context --
   never the raw conversation history -- via `carry_keys`.
2. **Independent entitlement resolution**: this module has no code path that
   copies, elevates, or otherwise reuses the origin agent's entitlement for
   the destination. `execute_handoff` dispatches through the exact same
   `AgentDispatcher` (EP-12-T01) any other call uses, which resolves the
   destination agent's own MCP Client credential from scratch
   (`AgentTokenProvider.token_for(target_agent)`) -- the Gateway/PDP
   (EP-05/EP-03) then reauthorizes independently, precisely as ADR-023
   requires (the Hoshikawa `agent_id`-in-payload anti-pattern this
   guards against).

A full LangGraph subgraph (intra-process handoff via a conditional
back-edge) is natural once a real multi-backend agent demo exists
(EP-13-T05, M4) -- this RI's own journey graph (EP-11) already has exactly
one active agent per run, so there is no intra-process edge to add yet;
this module is the cross-process/cross-backend handoff primitive that
EP-13-T05 will build its subgraph on top of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from emcp_bus.agent_runtime.dispatcher import DispatchResult
from emcp_bus.orchestrator.nba_model import NBADecision


class Dispatcher(Protocol):
    """What `execute_handoff` needs from `AgentDispatcher` (EP-12-T01) --
    narrower than the concrete class, so tests can exercise the
    minimization/independent-resolution guarantees below with a stub, and
    a real `AgentDispatcher` satisfies it structurally."""

    async def dispatch(self, nba: NBADecision, *, arguments: dict[str, Any]) -> DispatchResult: ...


@dataclass(frozen=True)
class HandoffPayload:
    decision_id: str
    origin_agent: str
    target_agent: str
    minimal_context: dict[str, Any]


def build_handoff_payload(
    *, nba: NBADecision, origin_agent: str, full_context: dict[str, Any], carry_keys: frozenset[str]
) -> HandoffPayload:
    """`full_context` might carry an entire journey's worth of state
    (profile, offerings, history, ...) -- only `carry_keys` survives into
    `minimal_context` (README.md §6.13: "contexto mínimo necessário)."""
    minimal_context = {key: value for key, value in full_context.items() if key in carry_keys}
    return HandoffPayload(
        decision_id=nba.decision_id,
        origin_agent=origin_agent,
        target_agent=nba.agent,
        minimal_context=minimal_context,
    )


async def execute_handoff(
    payload: HandoffPayload, nba: NBADecision, *, dispatcher: Dispatcher
) -> DispatchResult:
    """Dispatches to `payload.target_agent` -- `dispatcher` resolves that
    agent's own credential independently (EP-12-T01's `AgentTokenProvider`);
    nothing here ever reads or forwards `payload.origin_agent`'s credential."""
    if nba.agent != payload.target_agent:
        raise ValueError(
            f"nba.agent {nba.agent!r} does not match the handoff's target_agent "
            f"{payload.target_agent!r}"
        )
    return await dispatcher.dispatch(nba, arguments=payload.minimal_context)
