"""EP-01-T01: the *actual* Keycloak, not the JWKS-server stand-in the rest of
the e2e suite uses (see tests/e2e/conftest.py's module docstring). Real
Keycloak 26.7.3 container (Docker required -- skips otherwise), our real
`deploy/keycloak/realm-export.json`, real `client_credentials` grants, real
tokens validated by the real Gateway/PDP/Entitlement chain.

Session-scoped: Keycloak's cold start (schema init + realm import) takes
~15-20s, too slow to pay per-test. Gated on `docker` being on PATH, exactly
like `opa_url`/`OPA_BINARY` in conftest.py -- this whole file is skipped, not
failed, in an environment without Docker.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from emcp_bus.identity.authn import AuthenticationError, TokenValidator
from tests.e2e.conftest import RunningServer, free_port, set_current_gateway_port

REPO_ROOT = Path(__file__).parents[2]
REALM_EXPORT = REPO_ROOT / "deploy" / "keycloak" / "realm-export.json"

REALM_NAME = "emcp"
CLIENT_SECRETS = {
    "sales-read-agent": "dev-sales-read-agent-secret",
    "sales-write-agent": "dev-sales-write-agent-secret",
    "finance-payments-agent": "dev-finance-payments-agent-secret",
}


def _docker_binary() -> str | None:
    return shutil.which("docker")


@pytest.fixture(scope="session")
def keycloak_url() -> Iterator[str]:
    docker_binary = _docker_binary()
    if docker_binary is None:
        pytest.skip("docker not found on PATH -- required for the real-Keycloak suite")

    port = free_port()
    container_name = f"emcp-ri-test-keycloak-{port}"
    # `KC_HOSTNAME` fixed to `127.0.0.1:<port>` so every issued token's `iss`
    # matches what *this test* (running on the host) uses to reach it --
    # unlike docker-compose.yml's `keycloak` service, which fixes it to the
    # internal `keycloak:8080` DNS name instead, since there the Gateway
    # reaches it over the compose network, not localhost. Same underlying
    # gotcha either way: Keycloak derives `iss` from the request's Host
    # header unless pinned, so a token fetched via one path and validated
    # via another fails issuer validation for a boring reason.
    subprocess.run(
        [
            docker_binary,
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{port}:8080",
            "-e",
            "KC_BOOTSTRAP_ADMIN_USERNAME=admin",
            "-e",
            "KC_BOOTSTRAP_ADMIN_PASSWORD=admin",
            "-e",
            # Full URL form, not a bare "host:port" -- Keycloak 26's
            # `KC_HOSTNAME` only accepts a plain hostname or a complete URL
            # with scheme ("Provided hostname is neither a plain hostname
            # nor a valid URL" otherwise); a plain hostname alone can't carry
            # this test's dynamically allocated port.
            f"KC_HOSTNAME=http://127.0.0.1:{port}",
            "-e",
            "KC_HOSTNAME_STRICT=false",
            "-v",
            f"{REALM_EXPORT}:/opt/keycloak/data/import/realm-export.json:ro",
            "quay.io/keycloak/keycloak:26.7.3",
            "start-dev",
            "--import-realm",
        ],
        check=True,
        capture_output=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                response = httpx.get(f"{base_url}/realms/{REALM_NAME}", timeout=1)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Keycloak did not become ready in time")
        yield base_url
    finally:
        subprocess.run([docker_binary, "rm", "-f", container_name], capture_output=True)


def _fetch_token(keycloak_url: str, client_id: str) -> str:
    response = httpx.post(
        f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token",
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


# --- TokenValidator against real Keycloak (no Gateway involved) -----------


def test_real_keycloak_token_validates_with_the_real_azp_claim(keycloak_url: str) -> None:
    token = _fetch_token(keycloak_url, "sales-read-agent")
    validator = TokenValidator(
        jwks_url=f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/certs",
        issuer=f"{keycloak_url}/realms/{REALM_NAME}",
        audience="emcp-gateway",
    )

    authenticated = validator.validate(token)

    assert authenticated.client_id == "sales-read-agent"


def test_real_keycloak_token_rejected_for_wrong_audience(keycloak_url: str) -> None:
    token = _fetch_token(keycloak_url, "sales-read-agent")
    validator = TokenValidator(
        jwks_url=f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/certs",
        issuer=f"{keycloak_url}/realms/{REALM_NAME}",
        audience="some-other-resource-server",
    )

    with pytest.raises(AuthenticationError):
        validator.validate(token)


# --- Full Gateway chain against real Keycloak ------------------------------


@pytest.fixture
async def governed_stack_with_real_keycloak(
    monkeypatch: pytest.MonkeyPatch, opa_url: str, keycloak_url: str
) -> AsyncIterator[None]:
    """Same shape as conftest.py's `governed_stack`, except OIDC points at
    the real, dockerized Keycloak from `keycloak_url` instead of the JWKS
    stand-in the rest of the suite uses."""
    import uvicorn

    gateway_port = free_port()
    sales_port = free_port()

    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{sales_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv(
        "OIDC_JWKS_URL", f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/certs"
    )
    monkeypatch.setenv("OIDC_ISSUER", f"{keycloak_url}/realms/{REALM_NAME}")
    monkeypatch.setenv("OIDC_AUDIENCE", "emcp-gateway")
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "test-sales-domain-backend-credential")

    import example_mcp_servers.sales_domain.server as sales_module

    sales_server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=sales_port,
            log_level="warning",
        )
    )
    await sales_server.start()

    import emcp_bus.gateway.server as gateway_module

    auth_settings, token_verifier = gateway_module.build_auth()
    gateway_server = RunningServer(
        uvicorn.Config(
            gateway_module.build_app(auth_settings, token_verifier, host="127.0.0.1"),
            host="127.0.0.1",
            port=gateway_port,
            log_level="warning",
        )
    )
    await gateway_server.start()
    set_current_gateway_port(gateway_port)

    try:
        yield
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await sales_server.stop()


async def test_full_chain_with_real_keycloak_token(
    governed_stack_with_real_keycloak: None, keycloak_url: str
) -> None:
    """README.md §45 Teste 1, against a real IdP end to end: the Gateway
    validates a token *actually issued by Keycloak*, resolves the real
    Sales.Read entitlement, and reaches the real downstream Sales server."""
    from tests.e2e.conftest import run_against_gateway

    token = _fetch_token(keycloak_url, "sales-read-agent")

    tools = await run_against_gateway(lambda session: session.list_tools(), token=token)
    assert {t.name for t in tools.tools} == {
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
    }

    result = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
        token=token,
    )
    assert result.is_error is not True
    assert result.structured_content == {
        "customer_id": "cust-001",
        "name": "Aurora Ltda",
        "region": "BR-SP",
    }


async def test_cross_domain_denial_with_real_keycloak_token(
    governed_stack_with_real_keycloak: None, keycloak_url: str
) -> None:
    """A real Sales.Read token from real Keycloak still cannot reach Finance."""
    from tests.e2e.conftest import run_against_gateway

    token = _fetch_token(keycloak_url, "sales-read-agent")

    result = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", {"amount": 999}),
        token=token,
    )
    assert result.is_error is True
