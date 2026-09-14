"""Journey state (EP-11-T02, README.md §6.12).

A `TypedDict` (LangGraph's expected state-schema shape) carrying the journey
through the graph's fixed nodes: `resolve_profile -> resolve_entitlement ->
filter_offerings -> decide_nba -> approval_gate` (`graph.py`), plus the
denial-recalculation loop (EP-11-T04, `handle_denial_node`). `total=False`
because every field is populated incrementally, one node at a time -- the
graph's whole point is that a checkpoint mid-journey has some fields set and
others not yet.
"""

from __future__ import annotations

from typing import TypedDict

from emcp_bus.orchestrator.nba_model import NBADecision
from emcp_bus.profile_intelligence.models import ProfileView
from emcp_bus.registry.models import CapabilityManifest


class JourneyState(TypedDict, total=False):
    # Inputs (set by the caller before the first `invoke`).
    client_id: str
    raw_subject_id: str
    channel: str

    # Populated by resolve_profile.
    profile: ProfileView

    # Populated by resolve_entitlement.
    allowed_tools: list[str]
    entitlement_version: str
    risk_ceiling: str

    # Populated by filter_offerings.
    filtered_offerings: list[CapabilityManifest]

    # Populated by decide_nba.
    nba: NBADecision | None
    nba_requires_approval: bool

    # Populated by approval_gate (EP-11-T05).
    approval_status: str

    # Denial-recalculation loop (EP-11-T04) -- set by the caller (the Agent
    # Runtime, EP-12) when re-invoking the graph after a real Gateway DENY.
    denied_action: str | None
    excluded_actions: list[str]
    denial_outcome: str | None
