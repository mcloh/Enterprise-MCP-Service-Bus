"""Reference `ProfileIntelligenceProvider` (EP-09-T02, README.md §6.10, P7).

A deterministic, rules-over-synthetic-attributes stub -- not clustering, not
a trained model, not a proprietary taxonomy (P7: this RI does not attempt
"real" clustering without a real dataset, see docs/RI-PLANNING.md's gap
resolution). `ProfileIntelligenceProvider` is a `Protocol` so a production
fork can swap in a real ML-backed implementation without touching any
consumer (the Offering Filter, EP-10) -- the contract is `ProfileView` in,
`ProfileView` out.

Determinism (EP-09-T02 acceptance criterion: same subject_ref + same time
window -> same profileVersion) comes from hashing `(subject_ref, window)`
rather than anything time-of-call-dependent -- two resolutions in the same
ISO week for the same subject always agree, which is what a demo needs to
look "sensible" across repeated calls without a real model or a database of
prior scores.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Protocol

from emcp_bus.profile_intelligence.models import ProfileView, Segment

_ENGAGEMENT_BANDS = ("low", "medium", "high")
_CHANNEL_POOLS = (["app"], ["app", "email"], ["email", "sms"], ["app", "sms"])


class ProfileIntelligenceProvider(Protocol):
    def resolve(self, subject_ref: str, *, as_of: datetime | None = None) -> ProfileView: ...


class RuleBasedProfileProvider:
    """Reference implementation: `Segment` scores and `attributes` are
    derived purely from a hash of `(subject_ref, iso_week)` -- no external
    data source, no learned parameters. Good enough to demonstrate the
    contract (EP-10's Offering Filter, EP-11's DecisionContext) without
    claiming any real personalization intelligence.
    """

    def __init__(self, *, ttl: timedelta = timedelta(hours=24)) -> None:
        self._ttl = ttl

    def resolve(self, subject_ref: str, *, as_of: datetime | None = None) -> ProfileView:
        as_of = as_of or datetime.now(UTC)
        iso_year, iso_week, _ = as_of.isocalendar()
        window = f"{iso_year}-W{iso_week:02d}"
        digest = hashlib.sha256(f"{subject_ref}:{window}".encode()).hexdigest()

        engagement_band = _ENGAGEMENT_BANDS[int(digest[0], 16) % len(_ENGAGEMENT_BANDS)]
        preferred_channels = _CHANNEL_POOLS[int(digest[1], 16) % len(_CHANNEL_POOLS)]
        low_engagement_score = int(digest[2:4], 16) / 255
        digital_preference_score = int(digest[4:6], 16) / 255

        reason_codes = []
        if low_engagement_score > 0.5:
            reason_codes.append("LOW_RECENCY")
        if "app" in preferred_channels:
            reason_codes.append("APP_AFFINITY")

        return ProfileView(
            subject_ref=subject_ref,
            profile_version=f"rule-based-{window}-{digest[:8]}",
            segments=[
                Segment(id="low-engagement", score=round(low_engagement_score, 2)),
                Segment(id="digital-preference", score=round(digital_preference_score, 2)),
            ],
            attributes={
                "relationshipStage": "activation",
                "preferredChannels": ",".join(preferred_channels),
                "engagementBand": engagement_band,
            },
            reason_codes=reason_codes,
            expires_at=as_of + self._ttl,
        )
