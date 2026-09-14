"""Loads the RI's seed capability manifests (`config/capabilities/<domain>/*.yaml`)
through the real publishing pipeline (EP-02-T05) into a `RegistryStore`.

Shared by the Gateway's own startup (EP-06-T01: the Fabric router needs a
populated Registry to resolve anything) and by tests, so both exercise the
exact same load-and-publish path -- a schema mistake or a missing
`approval.required` on an R3 capability fails in both places identically.
"""

from __future__ import annotations

from pathlib import Path

from emcp_bus.common.config import load_yaml_models
from emcp_bus.registry.models import CapabilityManifest
from emcp_bus.registry.pipeline import PublishingPipeline
from emcp_bus.registry.store import RegistryStore


def load_all_capability_manifests(capabilities_dir: Path) -> list[CapabilityManifest]:
    manifests: list[CapabilityManifest] = []
    for domain_dir in sorted(capabilities_dir.iterdir()):
        if domain_dir.is_dir():
            manifests.extend(load_yaml_models(domain_dir, CapabilityManifest))
    return manifests


def publish_all(store: RegistryStore, manifests: list[CapabilityManifest]) -> None:
    pipeline = PublishingPipeline(store)
    for manifest in manifests:
        pipeline.submit(manifest)
        pipeline.publish(manifest.name)


def seed_registry(store: RegistryStore, capabilities_dir: Path) -> list[CapabilityManifest]:
    manifests = load_all_capability_manifests(capabilities_dir)
    publish_all(store, manifests)
    return manifests
