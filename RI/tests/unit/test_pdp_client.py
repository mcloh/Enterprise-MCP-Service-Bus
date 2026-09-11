"""PDPClient against a *real* OPA process (EP-03-T01/T04) -- not a mock.

Requires the `opa` binary on PATH (or `OPA_BINARY` pointing at it); skips
otherwise. See RI/README.md for install instructions -- OPA ships as a
single static binary, no Docker required.
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

from emcp_bus.pdp.client import PDPClient, PDPUnavailableError, compute_policy_version
from emcp_bus.pdp.models import PDPOutcome

POLICIES_DIR = Path(__file__).parents[2] / "config" / "policies"


def _opa_binary() -> str | None:
    return shutil.which(os.environ.get("OPA_BINARY", "opa"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def pdp_client() -> AsyncIterator[PDPClient]:
    opa_binary = _opa_binary()
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
    client = PDPClient(
        base_url=f"http://127.0.0.1:{port}",
        policy_version=compute_policy_version(POLICIES_DIR),
    )
    try:
        for _ in range(100):
            try:
                await client._http.get("/health")
                break
            except Exception:  # noqa: BLE001 -- retry loop, any error means "not ready yet"
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError("opa server did not become healthy in time")
        yield client
    finally:
        await client.aclose()
        process.terminate()
        process.wait(timeout=5)


async def test_policy_version_is_stable_and_nonempty() -> None:
    version = compute_policy_version(POLICIES_DIR)
    assert version
    assert version == compute_policy_version(POLICIES_DIR)


async def test_deny_when_tool_not_in_entitlement(pdp_client: PDPClient) -> None:
    await pdp_client.push_client_profile("Sales.Read", {"allowed_tools": ["sales.customer.get"]})

    decision = await pdp_client.evaluate(client_profile="Sales.Read", tool="finance.createPayment")

    assert decision.outcome is PDPOutcome.DENY
    assert decision.reason_code == "NOT_IN_ENTITLEMENT"
    assert decision.policy_version


async def test_allow_when_tool_in_entitlement_and_within_transaction_limits(
    pdp_client: PDPClient,
) -> None:
    await pdp_client.push_client_profile(
        "Sales.Write",
        {
            "allowed_tools": ["sales.quote.create"],
            "restrictions": {"max_transaction_value": 500000, "approval_threshold": 100000},
        },
    )

    decision = await pdp_client.evaluate(
        client_profile="Sales.Write",
        tool="sales.quote.create",
        arguments={"amount": 50000},
    )

    assert decision.outcome is PDPOutcome.ALLOW
    assert decision.reason_code == "ALLOWED"


async def test_deny_when_transaction_exceeds_limit_even_though_entitled(
    pdp_client: PDPClient,
) -> None:
    await pdp_client.push_client_profile(
        "Sales.Write",
        {
            "allowed_tools": ["sales.quote.create"],
            "restrictions": {"max_transaction_value": 500000},
        },
    )

    decision = await pdp_client.evaluate(
        client_profile="Sales.Write",
        tool="sales.quote.create",
        arguments={"amount": 999999},
    )

    assert decision.outcome is PDPOutcome.DENY
    assert decision.reason_code == "TRANSACTION_POLICY_DENIED"


async def test_require_approval_above_threshold(pdp_client: PDPClient) -> None:
    await pdp_client.push_client_profile(
        "Finance.Payments",
        {
            "allowed_tools": ["finance.payment.execute"],
            "restrictions": {"max_transaction_value": 10_000_000, "approval_threshold": 10_000},
        },
    )

    decision = await pdp_client.evaluate(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 15_000},
    )

    assert decision.outcome is PDPOutcome.REQUIRE_APPROVAL
    assert decision.reason_code == "APPROVAL_THRESHOLD_EXCEEDED"


async def test_fails_closed_when_opa_is_unreachable() -> None:
    unreachable_port = _free_port()  # nothing listening here
    client = PDPClient(base_url=f"http://127.0.0.1:{unreachable_port}", policy_version="dev")
    try:
        with pytest.raises(PDPUnavailableError):
            await client.evaluate(client_profile="Sales.Read", tool="sales.customer.get")
    finally:
        await client.aclose()
