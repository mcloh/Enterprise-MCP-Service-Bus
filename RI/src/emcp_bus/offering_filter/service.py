"""Offering Filter (EP-10-T01, README.md §6.11, §7.3, Axiom 8/11).

    FilteredOfferings(subject, client, context)
      = ActiveCatalog ∩ MaximumEntitlement(client) ∩ SubjectAndContextConstraints(subject, context)

The intersection order is deliberate and the middle term is never widened by
anything to its right: `allowed_tools` (EP-04's `ResolvedEntitlement`, i.e.
MaximumEntitlement) is applied first and is the only term this module treats
as security-relevant -- a `ProfileView` (EP-09) or `ConsentContext` can only
ever *narrow* what already survived that intersection, never reintroduce a
capability the client isn't entitled to (Axiom 8/11, README.md §6.11: "Uma
oferta ausente do maximum entitlement nunca pode ser reintroduzida por score
de perfil.").

`ConsentContext` here models one concrete, real `CapabilityManifest` field --
`data_classification` -- rather than inventing illustrative fields (region,
channel, ...) the manifest schema doesn't actually carry (README.md §6.11's
list is explicitly illustrative, not a fixed contract). A production fork
extending manifests with more context dimensions would extend this
dataclass and the one predicate in `_matches_context`, without touching the
security-relevant intersection above it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from emcp_bus.registry.models import CapabilityManifest, DataClassification


class ActiveCapabilitySource(Protocol):
    """What `OfferingFilterService` actually needs from a Registry --
    narrower than the full `RegistryStore` API (a real `RegistryStore`
    satisfies it structurally, no adapter needed), and lets property tests
    (EP-10-T02) exercise the filter's own set-arithmetic against a plain
    in-memory list of manifests, without paying real SQLite I/O per one of
    the 1000+ generated cases."""

    def list_active(self) -> list[CapabilityManifest]: ...


@dataclass(frozen=True)
class ConsentContext:
    allow_restricted_data: bool = False
    """Whether the subject has consented to capabilities whose
    `data_classification` includes `restricted` (README.md §6.11:
    "o filtro pode considerar ... consentimento")."""


_NO_CONSENT = ConsentContext()


class OfferingFilterService:
    def __init__(self, registry: ActiveCapabilitySource) -> None:
        self._registry = registry

    def filtered_offerings(
        self,
        *,
        allowed_tools: frozenset[str],
        context: ConsentContext = _NO_CONSENT,
    ) -> list[CapabilityManifest]:
        """`allowed_tools` is `ResolvedEntitlement.allowed_tools`
        (`emcp_bus.entitlement.manager`) -- MaximumEntitlement, already
        resolved and versioned by EP-04. Never pass anything else here."""
        active = self._registry.list_active()
        entitled = [manifest for manifest in active if manifest.name in allowed_tools]
        return [m for m in entitled if self._matches_context(m, context)]

    @staticmethod
    def _matches_context(manifest: CapabilityManifest, context: ConsentContext) -> bool:
        if context.allow_restricted_data:
            return True
        return DataClassification.RESTRICTED not in manifest.data_classification
