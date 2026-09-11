"""EntitlementManager against real OPA (EP-04-T02/T03/T04), loading the
actual YAML client profiles/registrations checked into config/ -- not
hand-built fixtures, so a schema or naming mistake in the YAML itself would
fail these tests too.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from emcp_bus.common.config import load_yaml_model, load_yaml_models
from emcp_bus.common.models import RiskTier
from emcp_bus.entitlement.manager import EntitlementManager, UnknownClientError
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.pdp.client import PDPClient, compute_policy_version

REPO_ROOT = Path(__file__).parents[2]
POLICIES_DIR = REPO_ROOT / "config" / "policies"
PROFILES_DIR = REPO_ROOT / "config" / "clients" / "profiles"
CLIENTS_DIR = REPO_ROOT / "config" / "clients"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def entitlement_manager() -> AsyncIterator[EntitlementManager]:
    opa_binary = shutil.which(os.environ.get("OPA_BINARY", "opa"))
    if opa_binary is None:
        pytest.skip(
            "opa binary not found on PATH (set OPA_BINARY or install it -- see RI/README.md)"
        )

    port = _free_port()
    process = subprocess.Popen(
        [opa_binary, "run", "--server", "--addr", f"127.0.0.1:{port}", str(POLICIES_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pdp = PDPClient(
        base_url=f"http://127.0.0.1:{port}",
        policy_version=compute_policy_version(POLICIES_DIR),
    )
    try:
        for _ in range(100):
            try:
                await pdp._http.get("/health")
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError("opa server did not become healthy in time")

        manager = EntitlementManager(pdp)
        manager.load_registrations(
            [
                load_yaml_model(path, ClientRegistration)
                for path in sorted(CLIENTS_DIR.glob("*.yaml"))
            ]
        )
        manager.load_profiles(load_yaml_models(PROFILES_DIR, ClientProfile))
        await manager.sync_profiles_to_pdp()
        yield manager
    finally:
        await pdp.aclose()
        process.terminate()
        process.wait(timeout=5)


async def test_resolves_sales_read_exactly_as_readme_7_1(
    entitlement_manager: EntitlementManager,
) -> None:
    resolved = entitlement_manager.resolve("sales-read-agent")

    assert resolved.profile_name == "Sales.Read"
    assert resolved.risk_ceiling is RiskTier.R1
    assert resolved.allowed_tools == frozenset(
        {
            "sales.customer.search",
            "sales.customer.get",
            "sales.order.get",
            "sales.inventory.check",
        }
    )
    assert resolved.entitlement_version


async def test_sales_write_does_not_include_approve_tools(
    entitlement_manager: EntitlementManager,
) -> None:
    resolved = entitlement_manager.resolve("sales-write-agent")

    assert "sales.quote.create" in resolved.allowed_tools
    assert "sales.discount.approve" not in resolved.allowed_tools
    assert "finance.createPayment" not in resolved.allowed_tools


async def test_unknown_client_id_raises() -> None:
    pdp = PDPClient(base_url="http://127.0.0.1:1", policy_version="dev")
    manager = EntitlementManager(pdp)
    try:
        with pytest.raises(UnknownClientError):
            manager.resolve("no-such-client")
    finally:
        await pdp.aclose()


async def test_revoke_client_forces_re_resolution_to_fail(
    entitlement_manager: EntitlementManager,
) -> None:
    entitlement_manager.resolve("sales-read-agent")  # populate cache
    assert entitlement_manager.cached("sales-read-agent") is not None

    entitlement_manager.revoke_client("sales-read-agent")

    assert entitlement_manager.cached("sales-read-agent") is None
    with pytest.raises(UnknownClientError):
        entitlement_manager.resolve("sales-read-agent")


async def test_revoke_profile_invalidates_cache_for_all_its_clients(
    entitlement_manager: EntitlementManager,
) -> None:
    entitlement_manager.resolve("sales-read-agent")
    assert entitlement_manager.cached("sales-read-agent") is not None

    entitlement_manager.revoke_profile("Sales.Read")

    assert entitlement_manager.cached("sales-read-agent") is None
    # Registration itself is untouched -- the *next* resolve() recomputes
    # cleanly against whatever profile is currently loaded (RF-08).
    resolved_again = entitlement_manager.resolve("sales-read-agent")
    assert resolved_again.profile_name == "Sales.Read"


async def test_entitlement_version_changes_when_profile_content_changes(
    entitlement_manager: EntitlementManager,
) -> None:
    before = entitlement_manager.resolve("sales-read-agent").entitlement_version

    mutated = ClientProfile.model_validate(
        {
            "name": "Sales.Read",
            "owner": "sales-platform",
            "risk_ceiling": "R1",
            "allowed_tools": ["sales.customer.get", "sales.order.get", "sales.inventory.check"],
        }
    )
    entitlement_manager.load_profiles([mutated])

    after = entitlement_manager.resolve("sales-read-agent").entitlement_version

    assert before != after
