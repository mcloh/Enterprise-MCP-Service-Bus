"""Conversational channel adapter (EP-12-T02, README.md §3.3, §6.13).

The one concrete channel adapter this RI demonstrates -- formats a dispatch
result as a conversational message for the `app` channel. A production
deployment would add adapters for push/media/campaign channels the same
way, each registered under its own `channel` value in a `ChannelRegistry`,
without changing `AgentDispatcher` (EP-12-T01) at all.
"""

from __future__ import annotations

from typing import Any

from emcp_bus.agent_runtime.dispatcher import DispatchResult
from emcp_bus.orchestrator.nba_model import NBADecision


class ConversationalChannelAdapter:
    channel = "app"

    async def deliver(self, nba: NBADecision, dispatch_result: DispatchResult) -> dict[str, Any]:
        if dispatch_result.status == "denied":
            message = f"I wasn't able to complete {nba.action} right now."
        else:
            message = f"Done: {nba.action} completed successfully."
        return {
            "channel": self.channel,
            "decision_id": nba.decision_id,
            "message": message,
            "status": dispatch_result.status,
        }
