"""Security acceptance suite (EP-15-T02, README.md §45): the 10 formal tests,
automated, running against the **real `docker-compose.yml`** (`core` +
`identity` profiles) -- a real `docker compose up --build`, a real Keycloak
container, a real containerized Gateway/OPA/Sales/Finance, not the
in-process fixtures the rest of this suite uses for speed.

Session-scoped: bringing the stack up (build + Keycloak cold start) costs
~30-60s, too slow to pay per test. Skipped, not failed, if `docker` is not
on PATH (matching `opa_url`/`keycloak_url` elsewhere in this suite).

Coverage note, for the 3 tests not implemented directly against this stack:

- **Teste 3 (prompt injection)** is reproduced with a *real* LLM in
  `tests/e2e/test_example_agent.py::test_prompt_injection_never_lets_a_sales_agent_execute_a_finance_payment`
  -- duplicating a full LLM-tool-calling round trip *and* a full Docker
  stack in the same test would be expensive for no additional coverage;
  the two independent dimensions (real LLM behavior, real containerized
  Gateway enforcement) are each proven once, not both at once.
- **Teste 6 (policy revocation)** has no HTTP-exposed "revoke" endpoint in
  this RI (`EntitlementManager.revoke_client`/`revoke_profile`, EP-04-T03,
  are in-process methods of a component a deployment embeds -- there is no
  admin API surfaced through the Gateway to trigger one from outside the
  process). It is exercised directly in `tests/unit/test_entitlement_manager.py`.
- **Teste 8 (token audience)** is proven against the same real Keycloak
  realm/config in
  `tests/e2e/test_real_keycloak.py::test_real_keycloak_token_rejected_for_wrong_audience`
  -- that file's Keycloak container uses the identical `deploy/keycloak/realm-export.json`
  this stack does, just launched via a bespoke `docker run` instead of this
  compose file, for a faster per-file fixture; the IdP config under test is
  the same either way.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import mcp_types as types
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)

REPO_ROOT = Path(__file__).parents[2]
REALM_NAME = "emcp"
GATEWAY_URL = "http://127.0.0.1:8000/mcp"
KEYCLOAK_URL = "http://127.0.0.1:8080"

CLIENT_SECRETS = {
    "sales-read-agent": "dev-sales-read-agent-secret",
    "sales-write-agent": "dev-sales-write-agent-secret",
    "finance-payments-agent": "dev-finance-payments-agent-secret",
}


def _docker_compose_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OIDC_JWKS_URL"] = f"http://keycloak:8080/realms/{REALM_NAME}/protocol/openid-connect/certs"
    env["OIDC_ISSUER"] = f"http://keycloak:8080/realms/{REALM_NAME}"
    env["OIDC_AUDIENCE"] = "emcp-gateway"
    return env


@pytest.fixture(scope="module")
def docker_stack() -> Iterator[None]:
    if shutil.which("docker") is None:
        pytest.skip("docker not found on PATH -- required for the docker-compose security suite")

    env = _docker_compose_env()
    subprocess.run(
        ["docker", "compose", "--profile", "core", "--profile", "identity", "up", "-d", "--build"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    try:
        for _ in range(120):
            try:
                if httpx.get(f"{KEYCLOAK_URL}/realms/{REALM_NAME}", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("keycloak did not become ready in the compose stack")

        for _ in range(60):
            try:
                token = _fetch_token("sales-read-agent")
                httpx.post(
                    GATEWAY_URL,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "acceptance-suite", "version": "0"},
                        },
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                    },
                    timeout=2,
                )
                break
            except httpx.HTTPError:
                time.sleep(1)
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "--profile", "core", "--profile", "identity", "down"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
        )


def _fetch_token(client_id: str) -> str:
    response = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": CLIENT_SECRETS[client_id],
        },
        timeout=5,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


async def _call_gateway(
    operation_name: str, arguments: dict[str, Any] | None, *, token: str | None
) -> types.ListToolsResult | types.CallToolResult:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(GATEWAY_URL, http_client=http_client) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        if operation_name == "tools/list":
            return await session.list_tools()
        assert arguments is not None
        return await session.call_tool(operation_name, arguments)


def _text(result: types.CallToolResult) -> str:
    return " ".join(getattr(item, "text", "") for item in result.content)


async def test_teste1_unauthorized_discovery_against_real_docker(docker_stack: None) -> None:
    token = _fetch_token("sales-read-agent")

    result = await _call_gateway("tools/list", None, token=token)

    assert isinstance(result, types.ListToolsResult)
    tool_names = {t.name for t in result.tools}
    assert "finance.payment.execute" not in tool_names


async def test_teste2_direct_unauthorized_call_against_real_docker(docker_stack: None) -> None:
    token = _fetch_token("sales-read-agent")

    result = await _call_gateway(
        "finance.payment.execute", {"payment_id": "pay-001", "amount": 1_000_000}, token=token
    )

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True


async def test_teste4_agent_role_spoofing_against_real_docker(docker_stack: None) -> None:
    token = _fetch_token("sales-read-agent")

    result = await _call_gateway(
        "finance.payment.execute",
        {"amount": 100, "role": "finance-admin", "client_profile": "Finance.Payments"},
        token=token,
    )

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True


async def test_teste5_cache_isolation_against_real_docker(docker_stack: None) -> None:
    sales_token = _fetch_token("sales-read-agent")
    finance_token = _fetch_token("finance-payments-agent")

    sales_result = await _call_gateway("tools/list", None, token=sales_token)
    finance_result = await _call_gateway("tools/list", None, token=finance_token)

    assert isinstance(sales_result, types.ListToolsResult)
    assert isinstance(finance_result, types.ListToolsResult)
    sales_names = {t.name for t in sales_result.tools}
    finance_names = {t.name for t in finance_result.tools}
    assert sales_names.isdisjoint(finance_names)
    assert sales_result.cache_scope == "private"
    assert finance_result.cache_scope == "private"


async def test_teste7_gateway_bypass_against_real_docker(docker_stack: None) -> None:
    """EP-05-T07: `sales-domain`/`finance-domain`/`opa` publish no host port
    in the real compose file -- a direct connection attempt from the host
    (outside the compose network) must fail."""
    with pytest.raises(httpx.HTTPError):
        httpx.get("http://127.0.0.1:8100/mcp", timeout=2)


async def test_teste9_backend_isolation_against_real_docker(docker_stack: None) -> None:
    """A tool a client IS entitled to must never reach a backend/resource
    the transaction policy excludes -- Sales.Write's quote.create above its
    own transaction limit is denied even though the tool itself is allowed."""
    token = _fetch_token("sales-write-agent")

    result = await _call_gateway(
        "sales.quote.create",
        {"customer_id": "cust-001", "amount": 999_999_999, "region": "BR-SP"},
        token=token,
    )

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    assert "TRANSACTION_POLICY_DENIED" in _text(result)


async def test_teste10_client_compromise_containment_against_real_docker(
    docker_stack: None,
) -> None:
    """A "stolen credential" (a real, validly-issued token for sales-read-agent)
    still cannot exceed that client's own MaximumEntitlement -- containment,
    not just correct discovery."""
    stolen_token = _fetch_token("sales-read-agent")

    tools_list = await _call_gateway("tools/list", None, token=stolen_token)
    assert isinstance(tools_list, types.ListToolsResult)
    assert {t.name for t in tools_list.tools} == {
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
    }

    write_attempt = await _call_gateway(
        "sales.quote.create", {"customer_id": "cust-001", "amount": 100}, token=stolen_token
    )
    assert isinstance(write_attempt, types.CallToolResult)
    assert write_attempt.is_error is True

    finance_attempt = await _call_gateway(
        "finance.payment.execute", {"payment_id": "pay-001", "amount": 100}, token=stolen_token
    )
    assert isinstance(finance_attempt, types.CallToolResult)
    assert finance_attempt.is_error is True
