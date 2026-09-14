"""Channel adapters (EP-12-T02, README.md §3.3/§6.13)."""

from __future__ import annotations

from datetime import datetime

import pytest

from emcp_bus.agent_runtime.channels.base import ChannelRegistry, UnsupportedChannelError
from emcp_bus.agent_runtime.channels.conversational import ConversationalChannelAdapter
from emcp_bus.agent_runtime.dispatcher import DispatchResult
from emcp_bus.orchestrator.nba_model import NBADecision


def _nba(channel: str = "app") -> NBADecision:
    return NBADecision(
        decision_id="dec-1",
        action="sales.customer.get",
        capability_version="1.0.0",
        subject_ref="subject:abc123",
        channel=channel,
        agent="engagement-assistant",
        reason_codes=["ELIGIBLE"],
        policy_context={},
        expires_at=datetime(2026, 1, 1),
    )


def test_channel_registry_routes_to_the_matching_adapter() -> None:
    registry = ChannelRegistry([ConversationalChannelAdapter()])

    adapter = registry.adapter_for("app")

    assert adapter.channel == "app"


def test_channel_registry_fails_explicitly_for_an_unsupported_channel() -> None:
    registry = ChannelRegistry([ConversationalChannelAdapter()])

    with pytest.raises(UnsupportedChannelError):
        registry.adapter_for("sms")


async def test_conversational_adapter_reports_success() -> None:
    adapter = ConversationalChannelAdapter()
    dispatch_result = DispatchResult(
        decision_id="dec-1",
        action="sales.customer.get",
        status="allowed",
        structured_content={"ok": True},
    )

    delivery = await adapter.deliver(_nba(), dispatch_result)

    assert delivery["status"] == "allowed"
    assert delivery["channel"] == "app"


async def test_conversational_adapter_reports_denial() -> None:
    adapter = ConversationalChannelAdapter()
    dispatch_result = DispatchResult(
        decision_id="dec-1", action="sales.customer.get", status="denied", structured_content=None
    )

    delivery = await adapter.deliver(_nba(), dispatch_result)

    assert delivery["status"] == "denied"
