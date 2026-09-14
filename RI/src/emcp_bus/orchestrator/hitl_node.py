"""Human-in-the-loop interrupt node (EP-11-T05, README.md §26, integrates EP-14).

Pauses the journey graph (LangGraph's `interrupt`) when the NBA's target
capability requires approval (`CapabilityManifest.approval.required`) --
the same signal the Gateway/PDP (EP-05/EP-14) enforce independently at
`tools/call` time, checked here *before* the Agent Runtime (EP-12) ever
attempts dispatch, so a high-risk NBA doesn't even reach the point of a
denied call.

No silent timeout: `interrupt()` suspends the graph and LangGraph persists
that via the checkpointer (verified in
tests/unit/test_orchestrator_graph.py) -- there is no code path here, or
anywhere in this module, that turns "no answer yet" into an implicit
approval. Resuming is the caller's job, via `Command(resume=...)` once
EP-14's `ApprovalService` reports a grant -- see `graph.py`'s module
docstring for how the two are wired together in a real deployment.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from emcp_bus.orchestrator.state import JourneyState


def requires_approval(offerings: list[Any], action: str) -> bool:
    return any(o.name == action and o.approval.required for o in offerings)


def approval_gate_node(state: JourneyState) -> dict[str, Any]:
    nba = state.get("nba")
    if nba is None:
        return {"approval_status": "not_applicable"}
    if not state.get("nba_requires_approval", False):
        return {"approval_status": "not_required"}

    decision = interrupt(
        {
            "approval_for": nba.action,
            "decision_id": nba.decision_id,
            "reason_codes": nba.reason_codes,
        }
    )
    return {"approval_status": "approved" if decision == "approved" else "denied"}
