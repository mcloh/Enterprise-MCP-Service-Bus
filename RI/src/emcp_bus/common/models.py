"""Shared value types used across config models (README.md §17, §41)."""

from __future__ import annotations

from enum import StrEnum


class RiskTier(StrEnum):
    """Capability/client risk classification (README.md §17).

    R0 discovery/public, R1 read, R2 write, R3 high-impact (approval-eligible),
    R4 destructive/restricted. The *same* enum is used for both a capability
    manifest's `risk_tier` (EP-02-T01) and a client profile's `risk_ceiling`
    (EP-04-T01) so entitlement resolution (EP-04-T02) can compare them
    directly instead of maintaining two parallel classifications.
    """

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


_ORDER: dict[RiskTier, int] = {tier: index for index, tier in enumerate(RiskTier)}


def risk_tier_at_or_below(tier: RiskTier, ceiling: RiskTier) -> bool:
    """True if `tier` is within `ceiling` (e.g. R1 <= R2, R3 > R2)."""
    return _ORDER[tier] <= _ORDER[ceiling]
