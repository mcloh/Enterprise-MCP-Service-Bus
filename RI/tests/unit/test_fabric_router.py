"""Fabric core capability router (EP-06-T01, README.md §6.7).

Real Registry (seeded from the actual config/capabilities/ manifests, same
as tests/unit/test_registry_seed_manifests.py) + real BackendCredentialProvider,
not hand-built fixtures -- a config mistake in either fails here too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emcp_bus.downstream.identity import BackendCredentialProvider
from emcp_bus.downstream.models import BackendConfig
from emcp_bus.fabric.router import CapabilityRouter, UnroutableCapabilityError
from emcp_bus.registry.models import LifecycleStatus
from emcp_bus.registry.seed import load_all_capability_manifests, publish_all
from emcp_bus.registry.store import RegistryStore

REPO_ROOT = Path(__file__).parents[2]
CAPABILITIES_DIR = REPO_ROOT / "config" / "capabilities"


@pytest.fixture
def router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CapabilityRouter:
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "sales-secret")
    monkeypatch.setenv("FINANCE_DOMAIN_SERVICE_TOKEN", "finance-secret")

    store = RegistryStore(tmp_path / "registry.db")
    publish_all(store, load_all_capability_manifests(CAPABILITIES_DIR))

    backend_credentials = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                service_account_token_env_var="SALES_DOMAIN_SERVICE_TOKEN",
            ),
            BackendConfig(
                backend="finance-domain",
                url="http://127.0.0.1:8101/mcp",
                audience="finance-domain-service",
                service_account_token_env_var="FINANCE_DOMAIN_SERVICE_TOKEN",
            ),
        ]
    )
    return CapabilityRouter(store, backend_credentials)


async def test_sales_capability_routes_to_sales_backend_not_finance(
    router: CapabilityRouter,
) -> None:
    """README.md §6.7 EP-06-T01 acceptance: a Sales capability must reach the
    Sales backend, never Finance."""
    route = await router.route("sales.customer.get")

    assert route.backend_id == "sales-domain"
    assert route.url == "http://127.0.0.1:8100/mcp"
    assert route.credential_token == "sales-secret"


async def test_finance_capability_routes_to_finance_backend(router: CapabilityRouter) -> None:
    route = await router.route("finance.payment.execute")

    assert route.backend_id == "finance-domain"
    assert route.url == "http://127.0.0.1:8101/mcp"
    assert route.credential_token == "finance-secret"


async def test_unknown_capability_is_unroutable(router: CapabilityRouter) -> None:
    with pytest.raises(UnroutableCapabilityError):
        await router.route("sales.does.not.exist")


async def test_deprecated_capability_is_unroutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only ACTIVE capabilities are routable (README.md §6.6) -- a capability
    that was published then deprecated must stop being reachable."""
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "sales-secret")
    store = RegistryStore(tmp_path / "registry.db")
    publish_all(store, load_all_capability_manifests(CAPABILITIES_DIR))
    store.set_lifecycle_status("sales.customer.get", LifecycleStatus.DEPRECATED)

    backend_credentials = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                service_account_token_env_var="SALES_DOMAIN_SERVICE_TOKEN",
            )
        ]
    )
    router = CapabilityRouter(store, backend_credentials)

    with pytest.raises(UnroutableCapabilityError):
        await router.route("sales.customer.get")


def test_distinct_backends_for_sales_only_entitlement_excludes_finance(
    router: CapabilityRouter,
) -> None:
    sales_read_tools = frozenset(
        {"sales.customer.search", "sales.customer.get", "sales.order.get", "sales.inventory.check"}
    )

    assert router.distinct_backends_for(sales_read_tools) == {"sales-domain"}


def test_distinct_backends_for_mixed_entitlement_includes_both(router: CapabilityRouter) -> None:
    mixed_tools = frozenset({"sales.customer.get", "finance.invoice.get"})

    assert router.distinct_backends_for(mixed_tools) == {"sales-domain", "finance-domain"}
