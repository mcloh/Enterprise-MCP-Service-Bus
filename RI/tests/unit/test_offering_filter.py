"""Offering Filter (EP-10-T01, README.md §6.11).

Real Registry seeded from the actual config/capabilities/ manifests, same
pattern as tests/unit/test_registry_seed_manifests.py / test_fabric_router.py.
"""

from __future__ import annotations

from pathlib import Path

from emcp_bus.offering_filter.service import ConsentContext, OfferingFilterService
from emcp_bus.registry.seed import load_all_capability_manifests, publish_all
from emcp_bus.registry.store import RegistryStore

REPO_ROOT = Path(__file__).parents[2]
CAPABILITIES_DIR = REPO_ROOT / "config" / "capabilities"


def _service(tmp_path: Path) -> OfferingFilterService:
    store = RegistryStore(tmp_path / "registry.db")
    publish_all(store, load_all_capability_manifests(CAPABILITIES_DIR))
    return OfferingFilterService(store)


def test_filtered_offerings_never_exceeds_the_allowed_tools_set(tmp_path: Path) -> None:
    service = _service(tmp_path)
    allowed_tools = frozenset({"sales.customer.get", "sales.order.get"})

    offerings = service.filtered_offerings(allowed_tools=allowed_tools)

    assert {m.name for m in offerings} == allowed_tools


def test_an_item_outside_entitlement_never_appears_regardless_of_catalog_size(
    tmp_path: Path,
) -> None:
    """README.md §6.11's core invariant, the single-case version of what
    test_offering_filter_invariants.py checks with 1000+ generated cases."""
    service = _service(tmp_path)
    allowed_tools = frozenset({"sales.customer.get"})  # finance.* deliberately excluded

    offerings = service.filtered_offerings(allowed_tools=allowed_tools)

    assert all(not m.name.startswith("finance.") for m in offerings)


def test_empty_entitlement_yields_no_offerings(tmp_path: Path) -> None:
    service = _service(tmp_path)

    offerings = service.filtered_offerings(allowed_tools=frozenset())

    assert offerings == []


def test_restricted_data_classification_excluded_without_consent(tmp_path: Path) -> None:
    """finance.payment.create/execute are data_classification: [confidential, restricted]
    (config/capabilities/finance/payment-*.yaml) -- excluded by default even
    when the client is entitled to them, absent explicit consent."""
    service = _service(tmp_path)
    allowed_tools = frozenset({"finance.payment.create", "finance.invoice.get"})

    offerings = service.filtered_offerings(allowed_tools=allowed_tools)

    names = {m.name for m in offerings}
    assert "finance.payment.create" not in names
    assert "finance.invoice.get" in names  # confidential only, not restricted


def test_restricted_data_classification_included_with_consent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    allowed_tools = frozenset({"finance.payment.create"})

    offerings = service.filtered_offerings(
        allowed_tools=allowed_tools, context=ConsentContext(allow_restricted_data=True)
    )

    assert {m.name for m in offerings} == {"finance.payment.create"}


def test_a_tool_not_in_the_active_registry_is_never_offered_even_if_entitled(
    tmp_path: Path,
) -> None:
    """MaximumEntitlement can name a tool the Registry doesn't know about
    (or has since deprecated) -- FilteredOfferings ⊆ ActiveCatalog too."""
    service = _service(tmp_path)
    allowed_tools = frozenset({"sales.customer.get", "sales.does.not.exist"})

    offerings = service.filtered_offerings(allowed_tools=allowed_tools)

    assert {m.name for m in offerings} == {"sales.customer.get"}
