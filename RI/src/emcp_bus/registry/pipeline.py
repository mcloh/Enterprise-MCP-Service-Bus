"""Capability publishing pipeline (EP-02-T02, README.md §6.8).

    Manifest -> [schema | risk | policy | backend gates] -> Gate -> Registry

Fails closed: any gate rejects the *whole* manifest, nothing partially
enters the Registry -- there is no ad hoc manual registration path (RF-11).
Schema/naming (name format, required fields) is already enforced by
`CapabilityManifest` itself at construction (EP-02-T01); the gates here are
the business rules a merely well-typed manifest can still violate.

A network health check of `backend.service` is a natural extension (README.md
§6.8: "health checks") intentionally left out of this milestone -- the RI has
no registry of backend health endpoints yet, and gating publication on one
would just be a `TODO` masquerading as a check.
"""

from __future__ import annotations

from emcp_bus.common.models import RiskTier
from emcp_bus.registry.lifecycle import validate_transition
from emcp_bus.registry.models import CapabilityManifest, LifecycleStatus
from emcp_bus.registry.store import RegistryStore

_HIGH_IMPACT_TIERS = frozenset({RiskTier.R3, RiskTier.R4})


class PublishingRejectedError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class PublishingPipeline:
    def __init__(self, store: RegistryStore) -> None:
        self._store = store

    def submit(self, manifest: CapabilityManifest) -> CapabilityManifest:
        """Runs `manifest` through the gates, then NOMINATE -> REVIEW -> REGISTER.

        Stops short of `ACTIVE` -- a registered capability is not yet
        resolvable by the Fabric until a separate `publish()` call, mirroring
        README.md §23's Register and Publish being distinct stages.
        """
        reasons = self._run_gates(manifest)
        if reasons:
            raise PublishingRejectedError(reasons)

        nominated = manifest.model_copy(
            update={
                "lifecycle": manifest.lifecycle.model_copy(
                    update={"status": LifecycleStatus.NOMINATE}
                )
            }
        )
        self._store.upsert(nominated)

        validate_transition(LifecycleStatus.NOMINATE, LifecycleStatus.REVIEW)
        self._store.set_lifecycle_status(manifest.name, LifecycleStatus.REVIEW)

        validate_transition(LifecycleStatus.REVIEW, LifecycleStatus.REGISTER)
        self._store.set_lifecycle_status(manifest.name, LifecycleStatus.REGISTER)

        return self._store.get(manifest.name)

    def publish(self, name: str) -> CapabilityManifest:
        """REGISTER -> ACTIVE: the capability becomes resolvable (README.md §23 "Publish")."""
        manifest = self._store.get(name)
        validate_transition(manifest.lifecycle.status, LifecycleStatus.ACTIVE)
        self._store.set_lifecycle_status(name, LifecycleStatus.ACTIVE)
        return self._store.get(name)

    def _run_gates(self, manifest: CapabilityManifest) -> list[str]:
        reasons: list[str] = []
        if not manifest.owner.strip():
            reasons.append("owner is required")
        if not manifest.backend.service.strip():
            reasons.append("backend.service is required")
        if manifest.risk_tier in _HIGH_IMPACT_TIERS and not manifest.approval.required:
            reasons.append(
                f"risk tier {manifest.risk_tier.value} requires approval.required=true "
                "(README.md §17)"
            )
        return reasons
