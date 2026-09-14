"""Property-based tests for the Offering Filter's subset invariant (EP-10-T02,
README.md §7.3):

    FilteredOfferings ⊆ MaximumEntitlement ⊆ GlobalCatalog

This module tests the two sub-invariants `OfferingFilterService` actually
enforces -- `FilteredOfferings ⊆ ActiveCatalog` and
`FilteredOfferings ⊆ MaximumEntitlement` -- against 1000+ randomly generated
(catalog, entitlement) pairs. `MaximumEntitlement ⊆ GlobalCatalog` is a
property of how client profiles are *authored* (EP-04, against real registry
names), not something the filter can or should assume about its own inputs
(a profile YAML can legitimately reference a tool the Registry has since
deprecated -- README.md §6.6 lifecycle -- and the filter's job is precisely
to drop that gracefully, see `test_offering_filter.py`'s
`test_a_tool_not_in_the_active_registry_is_never_offered_even_if_entitled`,
which exercises the real SQLite-backed `RegistryStore`).

Uses an in-memory `ActiveCapabilitySource` stand-in (real `CapabilityManifest`
instances, no SQLite) so 1000+ generated cases run in-process -- this is
testing `OfferingFilterService`'s own set arithmetic, not Registry
persistence (already covered by tests/unit/test_registry.py and
test_offering_filter.py's real-`RegistryStore` tests).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from emcp_bus.common.models import RiskTier
from emcp_bus.offering_filter.service import OfferingFilterService
from emcp_bus.registry.models import (
    ApprovalPolicy,
    BackendRef,
    CapabilityManifest,
    LifecycleInfo,
    LifecycleStatus,
)

_DOMAINS = ("sales", "finance", "hr")
_UNIVERSE = tuple(f"{domain}.capability{i}" for domain in _DOMAINS for i in range(8))
"""24 synthetic capability names spanning 3 domains -- large enough for
Hypothesis to explore meaningfully varied (catalog, entitlement) overlaps."""


def _manifest(name: str) -> CapabilityManifest:
    domain = name.split(".", 1)[0]
    return CapabilityManifest(
        name=name,
        version="1.0.0",
        domain=domain,
        owner=f"{domain}-team",
        risk_tier=RiskTier.R1,
        side_effects=False,
        idempotent=True,
        entitlements=["Any.Profile"],
        backend=BackendRef(type="mcp", service=f"{domain}-domain"),
        approval=ApprovalPolicy(),
        lifecycle=LifecycleInfo(status=LifecycleStatus.ACTIVE),
    )


class _InMemoryActiveCapabilitySource:
    def __init__(self, names: frozenset[str]) -> None:
        self._manifests = [_manifest(name) for name in names]

    def list_active(self) -> list[CapabilityManifest]:
        return self._manifests


@given(
    active_names=st.frozensets(st.sampled_from(_UNIVERSE)),
    allowed_tools=st.frozensets(st.sampled_from(_UNIVERSE)),
)
@settings(max_examples=1000)
def test_filtered_offerings_is_always_a_subset_of_both_catalog_and_entitlement(
    active_names: frozenset[str], allowed_tools: frozenset[str]
) -> None:
    service = OfferingFilterService(_InMemoryActiveCapabilitySource(active_names))

    offerings = service.filtered_offerings(allowed_tools=allowed_tools)
    offering_names = {m.name for m in offerings}

    assert offering_names <= active_names, "FilteredOfferings ⊆ ActiveCatalog violated"
    assert offering_names <= allowed_tools, "FilteredOfferings ⊆ MaximumEntitlement violated"


@given(
    active_names=st.frozensets(st.sampled_from(_UNIVERSE), min_size=1),
    excluded_name=st.sampled_from(_UNIVERSE),
)
@settings(max_examples=1000)
def test_an_item_outside_entitlement_never_appears_no_matter_the_catalog(
    active_names: frozenset[str], excluded_name: str
) -> None:
    """The concrete failure mode README.md §6.11 rules out: an item present
    in the catalog but absent from MaximumEntitlement must never leak into
    FilteredOfferings, regardless of what else is in the catalog."""
    allowed_tools = frozenset(active_names) - {excluded_name}

    service = OfferingFilterService(_InMemoryActiveCapabilitySource(active_names))
    offerings = service.filtered_offerings(allowed_tools=allowed_tools)

    assert excluded_name not in {m.name for m in offerings}
