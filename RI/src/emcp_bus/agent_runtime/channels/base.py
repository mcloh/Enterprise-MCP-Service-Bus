"""Channel adapter contract (EP-12-T02, README.md §3.3, §6.13).

Channel adapters encapsulate differences between experiences (app,
proactive/push, media/campaigns, ...) so the Agent Runtime's dispatch logic
(EP-12-T01) stays channel-agnostic. `ChannelRegistry.adapter_for` fails
loudly (`UnsupportedChannelError`) for an unregistered channel -- an
NBADecision with `channel="sms"` when no SMS adapter is registered must
never be silently dropped or misdelivered to the wrong channel.
"""

from __future__ import annotations

from typing import Any, Protocol

from emcp_bus.agent_runtime.dispatcher import DispatchResult
from emcp_bus.orchestrator.nba_model import NBADecision


class UnsupportedChannelError(Exception):
    pass


class ChannelAdapter(Protocol):
    channel: str

    async def deliver(self, nba: NBADecision, dispatch_result: DispatchResult) -> dict[str, Any]:
        """Formats `dispatch_result` for this channel's delivery mechanism
        and returns whatever the channel considers a delivery receipt --
        this RI's adapters return a plain dict; a production channel
        (push notification, SMS gateway, ...) would return that channel's
        own receipt shape instead."""
        ...


class ChannelRegistry:
    def __init__(self, adapters: list[ChannelAdapter]) -> None:
        self._adapters = {adapter.channel: adapter for adapter in adapters}

    def adapter_for(self, channel: str) -> ChannelAdapter:
        adapter = self._adapters.get(channel)
        if adapter is None:
            raise UnsupportedChannelError(
                f"No channel adapter registered for {channel!r} "
                f"(registered: {sorted(self._adapters)})"
            )
        return adapter
