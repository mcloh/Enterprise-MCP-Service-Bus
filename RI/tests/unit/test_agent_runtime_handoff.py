"""Agent-to-agent handoff (EP-12-T03, `could`, README.md §6.13, ADR-023)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from emcp_bus.agent_runtime.dispatcher import DispatchResult
from emcp_bus.agent_runtime.handoff_graph import build_handoff_payload, execute_handoff
from emcp_bus.orchestrator.nba_model import NBADecision


def _nba(agent: str) -> NBADecision:
    return NBADecision(
        decision_id="dec-1",
        action="finance.invoice.get",
        capability_version="1.0.0",
        subject_ref="subject:abc123",
        channel="app",
        agent=agent,
        reason_codes=["ELIGIBLE"],
        policy_context={},
        expires_at=datetime(2026, 1, 1),
    )


def test_build_handoff_payload_only_carries_declared_keys() -> None:
    nba = _nba("finance-specialist")
    full_context = {
        "customer_key": "cust-001",
        "conversation_history": ["a very long transcript..."],
        "internal_debug_state": {"secret": "irrelevant"},
    }

    payload = build_handoff_payload(
        nba=nba,
        origin_agent="engagement-assistant",
        full_context=full_context,
        carry_keys=frozenset({"customer_key"}),
    )

    assert payload.minimal_context == {"customer_key": "cust-001"}
    assert "conversation_history" not in payload.minimal_context
    assert "internal_debug_state" not in payload.minimal_context


def test_build_handoff_payload_records_origin_and_target() -> None:
    nba = _nba("finance-specialist")

    payload = build_handoff_payload(
        nba=nba, origin_agent="engagement-assistant", full_context={}, carry_keys=frozenset()
    )

    assert payload.origin_agent == "engagement-assistant"
    assert payload.target_agent == "finance-specialist"
    assert payload.decision_id == nba.decision_id


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[NBADecision, dict[str, Any]]] = []

    async def dispatch(self, nba: NBADecision, *, arguments: dict[str, Any]) -> DispatchResult:
        self.calls.append((nba, arguments))
        return DispatchResult(
            decision_id=nba.decision_id, action=nba.action, status="allowed", structured_content={}
        )


async def test_execute_handoff_dispatches_with_the_targets_own_nba_and_minimal_context() -> None:
    """The dispatcher call carries `nba` (whose `.agent` is the *target*) --
    `AgentDispatcher.dispatch` (EP-12-T01) resolves that agent's own
    credential from scratch. Nothing here ever touches the origin agent's
    token."""
    nba = _nba("finance-specialist")
    payload = build_handoff_payload(
        nba=nba,
        origin_agent="engagement-assistant",
        full_context={"customer_key": "cust-001", "history": "..."},
        carry_keys=frozenset({"customer_key"}),
    )
    dispatcher = _RecordingDispatcher()

    result = await execute_handoff(payload, nba, dispatcher=dispatcher)

    assert result.status == "allowed"
    assert len(dispatcher.calls) == 1
    called_nba, called_arguments = dispatcher.calls[0]
    assert called_nba.agent == "finance-specialist"
    assert called_arguments == {"customer_key": "cust-001"}


async def test_execute_handoff_rejects_a_mismatched_nba() -> None:
    nba_for_a_different_agent = _nba("some-other-agent")
    payload = build_handoff_payload(
        nba=_nba("finance-specialist"),
        origin_agent="engagement-assistant",
        full_context={},
        carry_keys=frozenset(),
    )

    with pytest.raises(ValueError, match="does not match"):
        await execute_handoff(payload, nba_for_a_different_agent, dispatcher=_RecordingDispatcher())
