"""EP-02-T05: the real seed manifests under config/capabilities/ go through the
real pipeline end to end -- not hand-built fixtures, so a schema mistake or a
missing `approval.required` on an R3 capability fails here too."""

from __future__ import annotations

from pathlib import Path

from emcp_bus.registry.models import LifecycleStatus
from emcp_bus.registry.seed import load_all_capability_manifests, publish_all
from emcp_bus.registry.store import RegistryStore

REPO_ROOT = Path(__file__).parents[2]
CAPABILITIES_DIR = REPO_ROOT / "config" / "capabilities"


def test_all_seed_manifests_publish_successfully(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.db")
    manifests = load_all_capability_manifests(CAPABILITIES_DIR)

    assert len(manifests) == 9  # 6 sales + 3 finance -- update this if seed data changes

    publish_all(store, manifests)

    active = store.list_active()
    assert len(active) == len(manifests)
    assert all(m.lifecycle.status is LifecycleStatus.ACTIVE for m in active)


def test_seed_manifests_by_domain(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.db")
    publish_all(store, load_all_capability_manifests(CAPABILITIES_DIR))

    sales_tools = {m.name for m in store.list_by_domain("sales")}
    finance_tools = {m.name for m in store.list_by_domain("finance")}

    assert sales_tools == {
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
        "sales.quote.create",
        "sales.quote.update",
    }
    assert finance_tools == {
        "finance.invoice.get",
        "finance.payment.create",
        "finance.payment.execute",
    }


def test_finance_payment_execute_is_r3_with_approval_required() -> None:
    manifests = {m.name: m for m in load_all_capability_manifests(CAPABILITIES_DIR)}
    payment_execute = manifests["finance.payment.execute"]

    assert payment_execute.risk_tier.value == "R3"
    assert payment_execute.approval.required is True
