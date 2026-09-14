"""Registry store + publishing pipeline + lifecycle state machine (EP-02-T02/T03/T04)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from emcp_bus.registry.lifecycle import InvalidLifecycleTransitionError, validate_transition
from emcp_bus.registry.models import CapabilityManifest, LifecycleStatus
from emcp_bus.registry.pipeline import PublishingPipeline, PublishingRejectedError
from emcp_bus.registry.store import CapabilityNotFoundError, RegistryStore


def _manifest(**overrides: object) -> CapabilityManifest:
    data: dict[str, object] = {
        "name": "sales.customer.get",
        "version": "1.0.0",
        "domain": "sales",
        "owner": "sales-platform",
        "risk_tier": "R1",
        "side_effects": False,
        "idempotent": True,
        "entitlements": ["Sales.Read"],
        "backend": {"type": "mcp", "service": "sales-domain"},
    }
    data.update(overrides)
    return CapabilityManifest.model_validate(data)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[RegistryStore]:
    yield RegistryStore(tmp_path / "registry.db")


def test_upsert_and_get_round_trip(store: RegistryStore) -> None:
    store.upsert(_manifest())

    fetched = store.get("sales.customer.get")

    assert fetched.owner == "sales-platform"
    assert fetched.risk_tier.value == "R1"


def test_get_missing_capability_raises(store: RegistryStore) -> None:
    with pytest.raises(CapabilityNotFoundError):
        store.get("no.such.capability")


def test_list_active_excludes_non_active_capabilities(store: RegistryStore) -> None:
    store.upsert(_manifest(name="sales.customer.get"))  # default lifecycle: NOMINATE
    active = _manifest(name="sales.order.get")
    active = active.model_copy(
        update={"lifecycle": active.lifecycle.model_copy(update={"status": LifecycleStatus.ACTIVE})}
    )
    store.upsert(active)

    result = store.list_active()

    assert [m.name for m in result] == ["sales.order.get"]


def test_list_by_domain_filters_correctly(store: RegistryStore) -> None:
    store.upsert(_manifest(name="sales.customer.get", domain="sales"))
    store.upsert(
        _manifest(
            name="finance.invoice.get",
            domain="finance",
            entitlements=["Finance.Read"],
            backend={"type": "mcp", "service": "finance-domain"},
        )
    )

    assert [m.name for m in store.list_by_domain("finance")] == ["finance.invoice.get"]


# --- lifecycle state machine ------------------------------------------------


def test_nominate_to_review_is_allowed() -> None:
    validate_transition(LifecycleStatus.NOMINATE, LifecycleStatus.REVIEW)


def test_nominate_directly_to_active_is_rejected() -> None:
    """The task's own acceptance criterion: never skip REVIEW on the way to ACTIVE."""
    with pytest.raises(InvalidLifecycleTransitionError):
        validate_transition(LifecycleStatus.NOMINATE, LifecycleStatus.ACTIVE)


def test_register_directly_to_active_requires_no_skip_but_is_the_publish_step() -> None:
    validate_transition(LifecycleStatus.REGISTER, LifecycleStatus.ACTIVE)


def test_retired_is_terminal() -> None:
    with pytest.raises(InvalidLifecycleTransitionError):
        validate_transition(LifecycleStatus.RETIRED, LifecycleStatus.ACTIVE)


# --- publishing pipeline -----------------------------------------------------


def test_pipeline_submit_then_publish_reaches_active(store: RegistryStore) -> None:
    pipeline = PublishingPipeline(store)

    registered = pipeline.submit(_manifest())
    assert registered.lifecycle.status is LifecycleStatus.REGISTER

    published = pipeline.publish("sales.customer.get")
    assert published.lifecycle.status is LifecycleStatus.ACTIVE


def test_pipeline_rejects_high_risk_capability_without_approval(store: RegistryStore) -> None:
    pipeline = PublishingPipeline(store)
    manifest = _manifest(
        name="finance.payment.execute",
        domain="finance",
        risk_tier="R3",
        side_effects=True,
        idempotent=False,
        entitlements=["Finance.Payments"],
        backend={"type": "mcp", "service": "finance-domain"},
    )

    with pytest.raises(PublishingRejectedError) as exc_info:
        pipeline.submit(manifest)

    assert any("approval" in reason for reason in exc_info.value.reasons)


def test_pipeline_accepts_high_risk_capability_with_approval_declared(store: RegistryStore) -> None:
    pipeline = PublishingPipeline(store)
    manifest = _manifest(
        name="finance.payment.execute",
        domain="finance",
        risk_tier="R3",
        side_effects=True,
        idempotent=False,
        entitlements=["Finance.Payments"],
        backend={"type": "mcp", "service": "finance-domain"},
        approval={"required": True},
    )

    registered = pipeline.submit(manifest)

    assert registered.lifecycle.status is LifecycleStatus.REGISTER


def test_pipeline_rejects_manifest_with_blank_owner(store: RegistryStore) -> None:
    pipeline = PublishingPipeline(store)

    with pytest.raises(PublishingRejectedError) as exc_info:
        pipeline.submit(_manifest(owner="  "))

    assert any("owner" in reason for reason in exc_info.value.reasons)


def test_publish_before_register_is_rejected(store: RegistryStore) -> None:
    """A manifest sitting in NOMINATE/REVIEW (e.g. review not yet approved)
    must not be publishable -- README.md §23 governance lifecycle."""
    store.upsert(_manifest())  # lifecycle defaults to NOMINATE

    pipeline = PublishingPipeline(store)
    with pytest.raises(InvalidLifecycleTransitionError):
        pipeline.publish("sales.customer.get")
