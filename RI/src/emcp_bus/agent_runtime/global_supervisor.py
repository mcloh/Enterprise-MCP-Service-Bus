"""Modo A -- Global Supervisor externo (EP-13-T05, ADR-024, README.md §6.2).

ADR-024 defines two equally valid integration modes for a multiagent
platform sitting on top of the E-MCP-BUS:

- **Modo A (governança-somente)**: an external Global Supervisor (e.g. the
  Agent Platform OCI reference, ADR-022's StateGraph/router) decides which
  backend agent handles a conversation turn. Our own Service Orchestrator
  (EP-11) does not participate in that decision at all.
- **Modo B (substituição completa, EP-13-T06)**: our own Service
  Orchestrator computes the NBA/NBO directly, and drives handoff through
  `emcp_bus.agent_runtime.handoff_graph.execute_handoff` with a real
  `NBADecision` (EP-11-T03).

`GlobalSupervisor` below is Modo A's stand-in for that external platform --
deliberately simple, keyword-based routing (it is not, and must never
become, a security boundary) that never touches `emcp_bus.orchestrator` at
all (checked mechanically in `tests/unit/test_agent_runtime_global_supervisor.py`,
the same AST-import discipline `identity_resolver.py`, EP-12-T04, uses for
the same reason). This is *why* `global_supervisor.py` does not build on
`handoff_graph.execute_handoff`/`AgentDispatcher.dispatch` even though both
already exist (EP-12-T01/T03): those consume an `NBADecision`, which only
our own Orchestrator produces -- requiring one here would silently turn
Modo A into Modo B.

The actual security property Modo A must uphold (EP-13-T05's acceptance
criteria) does not live in this module at all: it lives in the fact that
each `BackendAgent` this class routes to resolves its own MCP
Client/entitlement completely independently (its own bearer token, its own
`tools/list`, EP-01/EP-05/EP-03) -- `GlobalSupervisor` never reads, stores,
or forwards one backend's credential to another. Routing to the "wrong"
backend, or a backend being tricked by a prompt into wanting to act outside
its own catalog, is always still caught downstream by the real Gateway/PDP,
exactly as for a single-agent deployment (README.md §29).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

RouterFn = Callable[[str], "str | None"]
"""Picks a backend name from a message's content, or `None` to stay on the
current backend -- see `keyword_router` below for the reference implementation
and the module docstring for why routing quality is deliberately out of scope."""


class BackendAgent(Protocol):
    """What `GlobalSupervisor` needs from a backend agent -- structurally
    typed (not `agents.example_agent.agent.ExampleAgent` directly) so this
    core-library module never imports from `agents/` (example/demo code),
    matching the discipline `dispatcher.py`'s `AgentTokenProvider` already
    applies to credentials."""

    async def run_turn(self, message: str) -> object: ...


@dataclass(frozen=True)
class RoutingResult:
    backend_name: str
    handed_off: bool
    """True if this turn was routed to a *different* backend than
    `current_backend` -- the caller/demo UI can use this to render "you are
    now speaking with billing" or similar, purely cosmetic."""
    turn_result: object


class UnknownBackendError(Exception):
    pass


class GlobalSupervisor:
    def __init__(self, backends: dict[str, BackendAgent]) -> None:
        if not backends:
            raise ValueError("GlobalSupervisor needs at least one backend")
        self._backends = dict(backends)

    async def route_and_run(
        self, message: str, *, current_backend: str, router: RouterFn
    ) -> RoutingResult:
        """`router` picks a backend name (or `None` to stay on
        `current_backend`) from the message content alone -- a real
        deployment plugs in whatever routing intelligence the external
        platform provides (an LLM-based intent classifier, a rules engine,
        ...); this RI ships `keyword_router` below as a minimal, honest
        stand-in, not a claim about routing quality."""
        if current_backend not in self._backends:
            raise UnknownBackendError(current_backend)

        target = router(message) or current_backend
        if target not in self._backends:
            target = current_backend

        result = await self._backends[target].run_turn(message)
        return RoutingResult(
            backend_name=target, handed_off=target != current_backend, turn_result=result
        )


def keyword_router(message: str, *, routes: dict[str, frozenset[str]] | None = None) -> str | None:
    """Minimal reference router: the first backend whose keyword set
    appears in `message` (case-insensitive), else `None` (stay put). Not
    the security boundary (see module docstring) -- just enough to
    demonstrate a real handoff decision without requiring a second LLM
    call to make it."""
    routes = routes or {
        "finance_agent": frozenset({"invoice", "invoices", "pay", "payment", "bill", "billing"})
    }
    lowered = message.lower()
    for backend_name, keywords in routes.items():
        if any(keyword in lowered for keyword in keywords):
            return backend_name
    return None
