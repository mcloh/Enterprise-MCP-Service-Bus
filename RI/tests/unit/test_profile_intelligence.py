"""Profile Intelligence (EP-09, README.md §6.10, Axiom 11)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from emcp_bus.profile_intelligence.governance import (
    DriftMonitor,
    FeatureLineageLog,
    SensitiveAttributeLeakageError,
    assert_no_raw_pii,
    pseudonymize_subject,
)
from emcp_bus.profile_intelligence.models import ProfileView, Segment
from emcp_bus.profile_intelligence.rule_based_provider import RuleBasedProfileProvider


def test_profile_view_requires_expires_at() -> None:
    with pytest.raises(ValidationError):
        ProfileView(subject_ref="subject:abc123", profile_version="v1")  # type: ignore[call-arg]


def test_profile_view_requires_profile_version() -> None:
    with pytest.raises(ValidationError):
        ProfileView(  # type: ignore[call-arg]
            subject_ref="subject:abc123", expires_at=datetime(2026, 1, 1)
        )


def test_segment_score_must_be_within_unit_interval() -> None:
    with pytest.raises(ValidationError):
        Segment(id="low-engagement", score=1.5)


# --- EP-09-T02: rule-based provider -----------------------------------------


def test_rule_based_provider_is_deterministic_for_same_subject_and_window() -> None:
    provider = RuleBasedProfileProvider()
    as_of = datetime(2026, 9, 14)

    first = provider.resolve("subject:7f31c2", as_of=as_of)
    second = provider.resolve("subject:7f31c2", as_of=as_of)

    assert first.profile_version == second.profile_version
    assert first.segments == second.segments
    assert first.attributes == second.attributes


def test_rule_based_provider_differs_across_subjects() -> None:
    provider = RuleBasedProfileProvider()
    as_of = datetime(2026, 9, 14)

    first = provider.resolve("subject:aaaaaa", as_of=as_of)
    second = provider.resolve("subject:bbbbbb", as_of=as_of)

    assert first.profile_version != second.profile_version


def test_rule_based_provider_differs_across_time_windows() -> None:
    provider = RuleBasedProfileProvider()

    week_one = provider.resolve("subject:7f31c2", as_of=datetime(2026, 1, 5))
    week_ten = provider.resolve("subject:7f31c2", as_of=datetime(2026, 3, 9))

    assert week_one.profile_version != week_ten.profile_version


def test_rule_based_provider_never_produces_a_raw_subject_ref() -> None:
    """The provider itself never invents a subject_ref -- it only echoes
    back whatever it was given, so pseudonymization is the caller's job
    (governance.pseudonymize_subject) applied *before* calling resolve()."""
    provider = RuleBasedProfileProvider()

    result = provider.resolve(pseudonymize_subject("customer-raw-id-001"))

    assert_no_raw_pii(result)  # must not raise


# --- EP-09-T03: governance ---------------------------------------------------


def test_pseudonymize_subject_is_deterministic() -> None:
    assert pseudonymize_subject("raw-id") == pseudonymize_subject("raw-id")


def test_pseudonymize_subject_differs_for_different_inputs() -> None:
    assert pseudonymize_subject("raw-id-1") != pseudonymize_subject("raw-id-2")


def test_assert_no_raw_pii_rejects_non_pseudonymized_subject_ref() -> None:
    profile = ProfileView(
        subject_ref="customer-001",  # a raw id, not "subject:<hash>"
        profile_version="v1",
        expires_at=datetime(2026, 1, 1),
    )

    with pytest.raises(SensitiveAttributeLeakageError):
        assert_no_raw_pii(profile)


def test_assert_no_raw_pii_rejects_pii_looking_attribute_key() -> None:
    profile = ProfileView(
        subject_ref="subject:abc123",
        profile_version="v1",
        attributes={"email": "someone@example.com"},
        expires_at=datetime(2026, 1, 1),
    )

    with pytest.raises(SensitiveAttributeLeakageError):
        assert_no_raw_pii(profile)


def test_assert_no_raw_pii_accepts_a_clean_profile_view() -> None:
    profile = ProfileView(
        subject_ref="subject:abc123",
        profile_version="v1",
        attributes={"engagementBand": "low"},
        expires_at=datetime(2026, 1, 1),
    )

    assert_no_raw_pii(profile)  # must not raise


def test_feature_lineage_log_records_an_entry_per_resolution() -> None:
    log = FeatureLineageLog()
    profile = ProfileView(
        subject_ref="subject:abc123", profile_version="v1", expires_at=datetime(2026, 1, 1)
    )

    entry = log.record(
        profile,
        features=("recency", "channel_affinity"),
        purpose="personalization",
        time_window="2026-W37",
    )

    assert log.records == [entry]
    assert entry.subject_ref == "subject:abc123"
    assert entry.features == ("recency", "channel_affinity")


def test_drift_monitor_flags_a_large_score_delta() -> None:
    monitor = DriftMonitor(threshold=0.3)
    profile = ProfileView(
        subject_ref="subject:abc123",
        profile_version="v1",
        segments=[Segment(id="low-engagement", score=0.9)],
        expires_at=datetime(2026, 1, 1),
    )

    reports = monitor.check(profile, baseline={"low-engagement": 0.2})

    assert len(reports) == 1
    assert reports[0].drifted is True


def test_drift_monitor_does_not_flag_a_small_score_delta() -> None:
    monitor = DriftMonitor(threshold=0.3)
    profile = ProfileView(
        subject_ref="subject:abc123",
        profile_version="v1",
        segments=[Segment(id="low-engagement", score=0.5)],
        expires_at=datetime(2026, 1, 1),
    )

    reports = monitor.check(profile, baseline={"low-engagement": 0.45})

    assert len(reports) == 1
    assert reports[0].drifted is False
