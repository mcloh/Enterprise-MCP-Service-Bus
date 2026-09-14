"""Data-governance guardrails for Profile Intelligence (EP-09-T03, README.md
§6.10, Threat: Sensitive attribute leakage §28).

Three requirements from README §6.10's governance list, made concrete and
testable: pseudonymized subject identifiers, a lineage record per resolution
(features/version/window), and a drift-monitor *stub* -- explicitly not real
statistical drift detection (P7: no real dataset to detect drift against in
this RI), just the extension point a production fork would wire a real one
into.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from emcp_bus.profile_intelligence.models import ProfileView

_SENSITIVE_ATTRIBUTE_KEY_MARKERS = (
    "email",
    "cpf",
    "ssn",
    "phone",
    "name",
    "address",
    "birthdate",
    "document",
)


def pseudonymize_subject(raw_identifier: str) -> str:
    """A raw identifier (customer id, email, msisdn, ...) is never carried
    into a `ProfileView` -- only this deterministic pseudonym is."""
    digest = hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()
    return f"subject:{digest[:6]}"


class SensitiveAttributeLeakageError(Exception):
    """A `ProfileView` carries a raw (non-pseudonymized) subject reference,
    or an `attributes` key that looks like direct PII -- README.md §28's
    "Sensitive attribute leakage" threat, made a hard failure rather than a
    lint warning."""


def assert_no_raw_pii(profile_view: ProfileView) -> None:
    if not profile_view.subject_ref.startswith("subject:"):
        raise SensitiveAttributeLeakageError(
            f"ProfileView.subject_ref {profile_view.subject_ref!r} is not pseudonymized "
            "(expected 'subject:<hash>', see pseudonymize_subject)"
        )
    for key in profile_view.attributes:
        lowered = key.lower()
        if any(marker in lowered for marker in _SENSITIVE_ATTRIBUTE_KEY_MARKERS):
            raise SensitiveAttributeLeakageError(
                f"ProfileView.attributes key {key!r} looks like direct PII, not a "
                "derived/synthetic attribute (README.md §28)"
            )


@dataclass(frozen=True)
class FeatureLineageRecord:
    """Documents *why* a ProfileView looks the way it does -- README.md
    §6.10: "documentar features, finalidade, janela temporal e qualidade"."""

    subject_ref: str
    profile_version: str
    features: tuple[str, ...]
    purpose: str
    time_window: str
    resolved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FeatureLineageLog:
    """In-memory append-only lineage log -- a JSONL/DB-backed sink is a
    natural production extension (same shape as `emcp_bus.audit.sink`), not
    needed for this RI's demonstration scope."""

    def __init__(self) -> None:
        self.records: list[FeatureLineageRecord] = []

    def record(
        self,
        profile_view: ProfileView,
        *,
        features: tuple[str, ...],
        purpose: str,
        time_window: str,
    ) -> FeatureLineageRecord:
        entry = FeatureLineageRecord(
            subject_ref=profile_view.subject_ref,
            profile_version=profile_view.profile_version,
            features=features,
            purpose=purpose,
            time_window=time_window,
        )
        self.records.append(entry)
        return entry


@dataclass(frozen=True)
class DriftReport:
    segment_id: str
    baseline_score: float
    observed_score: float
    drifted: bool


class DriftMonitor:
    """Stub (README.md §6.10: "monitorar drift, estabilidade e impacto
    desigual") -- flags a segment whose score moved further than
    `threshold` from a caller-supplied baseline. Not real statistical drift
    detection (no population-level distribution tracking); a production
    fork with real telemetry would replace this, not extend it.
    """

    def __init__(self, *, threshold: float = 0.3) -> None:
        self._threshold = threshold

    def check(self, profile_view: ProfileView, baseline: dict[str, float]) -> list[DriftReport]:
        reports = []
        for segment in profile_view.segments:
            baseline_score = baseline.get(segment.id)
            if baseline_score is None:
                continue
            delta = abs(segment.score - baseline_score)
            reports.append(
                DriftReport(
                    segment_id=segment.id,
                    baseline_score=baseline_score,
                    observed_score=segment.score,
                    drifted=delta > self._threshold,
                )
            )
        return reports
