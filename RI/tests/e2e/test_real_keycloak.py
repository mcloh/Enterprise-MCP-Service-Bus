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
from datetime import UTC, datetime, timedelta
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


# --- RFC 8693 token exchange against real Keycloak (EP-07) -----------------
#
# `deploy/keycloak/realm-export.json` registers a `gateway-token-exchange`
# client (`standard.token.exchange.enabled: true`, Keycloak 26.2+ Standard
# Token Exchange -- GA, no preview feature flag) plus two audience-only
# placeholder clients (`sales-domain-service`/`finance-domain-service`,
# never used to log in) and two client scopes (`aud-sales-domain-service`/
# `aud-finance-domain-service`, each an `oidc-audience-mapper` targeting one
# placeholder client) as `gateway-token-exchange`'s default scopes. Verified
# empirically while building this: Keycloak's `audience` exchange parameter
# only accepts a *registered client id* (a free-form/"custom" audience
# string fails with "Audience not found"), and requesting `audience` alone
# without a `scope` that actually adds it fails with "Requested audience not
# available" -- both real IdP behaviors, not something this RI's code layer
# could have gotten right by API contract alone.


async def test_real_token_exchange_produces_a_token_scoped_to_sales_domain(
    keycloak_url: str,
) -> None:
    import base64
    import json

    from emcp_bus.downstream.identity import BackendCredentialProvider, TokenExchangeClient
    from emcp_bus.downstream.models import BackendConfig

    exchange_client = TokenExchangeClient(
        "gateway-token-exchange", "dev-gateway-token-exchange-secret"
    )
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                credential_mode="token_exchange",
                token_exchange_endpoint=(
                    f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
                ),
                token_exchange_scope="aud-sales-domain-service",
            )
        ],
        token_exchange_client=exchange_client,
    )

    try:
        credential = await provider.credential_for("sales-domain")
    finally:
        await exchange_client.aclose()

    assert credential.audience == "sales-domain-service"
    payload = credential.token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    assert claims["aud"] == "sales-domain-service"
    assert claims["azp"] == "gateway-token-exchange"


async def test_real_token_exchange_never_reuses_the_same_token_across_different_backends(
    keycloak_url: str,
) -> None:
    """The exchanged credential for one backend must never satisfy another --
    each backend gets its own `aud` claim, exchanged independently."""
    from emcp_bus.downstream.identity import BackendCredentialProvider, TokenExchangeClient
    from emcp_bus.downstream.models import BackendConfig

    endpoint = f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
    exchange_client = TokenExchangeClient(
        "gateway-token-exchange", "dev-gateway-token-exchange-secret"
    )
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                credential_mode="token_exchange",
                token_exchange_endpoint=endpoint,
                token_exchange_scope="aud-sales-domain-service",
            ),
            BackendConfig(
                backend="finance-domain",
                url="http://127.0.0.1:8101/mcp",
                audience="finance-domain-service",
                credential_mode="token_exchange",
                token_exchange_endpoint=endpoint,
                token_exchange_scope="aud-finance-domain-service",
            ),
        ],
        token_exchange_client=exchange_client,
    )

    try:
        sales_credential = await provider.credential_for("sales-domain")
        finance_credential = await provider.credential_for("finance-domain")
    finally:
        await exchange_client.aclose()

    assert sales_credential.token != finance_credential.token
    assert sales_credential.audience == "sales-domain-service"
    assert finance_credential.audience == "finance-domain-service"


async def test_full_gateway_chain_with_token_exchange_backend_credential(
    monkeypatch: pytest.MonkeyPatch, opa_url: str, keycloak_url: str, tmp_path: Path
) -> None:
    """EP-07 end to end through the real Gateway: `sales-domain`'s backend
    credential comes from a real RFC 8693 exchange (not
    `SALES_DOMAIN_SERVICE_TOKEN`), and the resulting `tools/call` still
    reaches the real Sales backend -- proving the whole path, not just the
    identity layer in isolation (the two tests above)."""
    import shutil as shutil_module

    import uvicorn

    from tests.e2e.conftest import (
        RunningServer,
        free_port,
        run_against_gateway,
        set_current_gateway_port,
    )

    # A private copy of config/ with sales-domain switched to token_exchange
    # mode -- never mutate the real config/backends/sales-domain.yaml, which
    # every other e2e test relies on being in `service_account` mode.
    config_copy = tmp_path / "config"
    shutil_module.copytree(REPO_ROOT / "config", config_copy)
    token_endpoint = f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
    (config_copy / "backends" / "sales-domain.yaml").write_text(
        "backend: sales-domain\n"
        "url: ${SALES_DOMAIN_URL:-http://127.0.0.1:8100/mcp}\n"
        "audience: sales-domain-service\n"
        "credential_mode: token_exchange\n"
        f"token_exchange_endpoint: {token_endpoint}\n"
        "token_exchange_scope: aud-sales-domain-service\n",
        encoding="utf-8",
    )

    gateway_port = free_port()
    sales_port = free_port()

    monkeypatch.setenv("EMCP_CONFIG_DIR", str(config_copy))
    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{sales_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv(
        "OIDC_JWKS_URL", f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/certs"
    )
    monkeypatch.setenv("OIDC_ISSUER", f"{keycloak_url}/realms/{REALM_NAME}")
    monkeypatch.setenv("OIDC_AUDIENCE", "emcp-gateway")
    monkeypatch.setenv("GATEWAY_TOKEN_EXCHANGE_CLIENT_ID", "gateway-token-exchange")
    monkeypatch.setenv("GATEWAY_TOKEN_EXCHANGE_CLIENT_SECRET", "dev-gateway-token-exchange-secret")
    monkeypatch.delenv("SALES_DOMAIN_SERVICE_TOKEN", raising=False)  # must not be needed anymore

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
        token = _fetch_token(keycloak_url, "sales-read-agent")
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
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await sales_server.stop()


# --- EP-12-T01: AgentDispatcher against a real Gateway + real Keycloak -----


async def test_agent_dispatcher_reaches_the_real_backend_through_the_real_gateway(
    governed_stack_with_real_keycloak: None, keycloak_url: str
) -> None:
    """The Agent Runtime never generates or stores its own credential
    (EP-12-T01 acceptance criterion) -- `OIDCAgentTokenProvider` obtains a
    real token for `sales-read-agent`'s already-registered MCP Client via a
    real `client_credentials` grant, and `AgentDispatcher` uses only that to
    reach the real Sales backend through the real Gateway/PDP chain."""
    from emcp_bus.agent_runtime.dispatcher import (
        AgentClientCredentials,
        AgentDispatcher,
        OIDCAgentTokenProvider,
    )
    from emcp_bus.orchestrator.nba_model import NBADecision
    from tests.e2e.conftest import _gateway_url

    token_endpoint = f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
    token_provider = OIDCAgentTokenProvider(
        {
            "sales-read-agent": AgentClientCredentials(
                client_id="sales-read-agent",
                client_secret=CLIENT_SECRETS["sales-read-agent"],
                token_endpoint=token_endpoint,
            )
        }
    )
    dispatcher = AgentDispatcher(gateway_url=_gateway_url(), token_provider=token_provider)
    nba = NBADecision(
        decision_id="dec-e2e-1",
        action="sales.customer.get",
        capability_version="1.0.0",
        subject_ref="subject:abc123",
        channel="app",
        agent="sales-read-agent",
        reason_codes=["ELIGIBLE"],
        policy_context={},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    try:
        result = await dispatcher.dispatch(nba, arguments={"customer_id": "cust-001"})
    finally:
        await token_provider.aclose()

    assert result.status == "allowed"
    assert result.structured_content == {
        "customer_id": "cust-001",
        "name": "Aurora Ltda",
        "region": "BR-SP",
    }


async def test_agent_dispatcher_denies_a_client_reaching_outside_its_entitlement(
    governed_stack_with_real_keycloak: None, keycloak_url: str
) -> None:
    """The exact same Gateway/PDP chain -- `sales-read-agent`'s own real
    token still cannot reach `finance.payment.execute`."""
    from emcp_bus.agent_runtime.dispatcher import (
        AgentClientCredentials,
        AgentDispatcher,
        OIDCAgentTokenProvider,
    )
    from emcp_bus.orchestrator.nba_model import NBADecision
    from tests.e2e.conftest import _gateway_url

    token_endpoint = f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
    token_provider = OIDCAgentTokenProvider(
        {
            "sales-read-agent": AgentClientCredentials(
                client_id="sales-read-agent",
                client_secret=CLIENT_SECRETS["sales-read-agent"],
                token_endpoint=token_endpoint,
            )
        }
    )
    dispatcher = AgentDispatcher(gateway_url=_gateway_url(), token_provider=token_provider)
    nba = NBADecision(
        decision_id="dec-e2e-2",
        action="finance.payment.execute",
        capability_version="1.0.0",
        subject_ref="subject:abc123",
        channel="app",
        agent="sales-read-agent",
        reason_codes=["ELIGIBLE"],
        policy_context={},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    try:
        result = await dispatcher.dispatch(nba, arguments={"amount": 999})
    finally:
        await token_provider.aclose()

    assert result.status == "denied"


async def test_two_agents_get_independently_resolved_tokens(
    governed_stack_with_real_keycloak: None, keycloak_url: str
) -> None:
    """EP-12-T03's core guarantee, proven with two real, distinct MCP
    Clients: `OIDCAgentTokenProvider` never reuses one agent's token for
    another -- each `client_credentials` grant is independent."""
    from emcp_bus.agent_runtime.dispatcher import AgentClientCredentials, OIDCAgentTokenProvider

    token_endpoint = f"{keycloak_url}/realms/{REALM_NAME}/protocol/openid-connect/token"
    token_provider = OIDCAgentTokenProvider(
        {
            "sales-read-agent": AgentClientCredentials(
                client_id="sales-read-agent",
                client_secret=CLIENT_SECRETS["sales-read-agent"],
                token_endpoint=token_endpoint,
            ),
            "finance-payments-agent": AgentClientCredentials(
                client_id="finance-payments-agent",
                client_secret=CLIENT_SECRETS["finance-payments-agent"],
                token_endpoint=token_endpoint,
            ),
        }
    )

    try:
        sales_token = await token_provider.token_for("sales-read-agent")
        finance_token = await token_provider.token_for("finance-payments-agent")
    finally:
        await token_provider.aclose()

    assert sales_token != finance_token
