"""Outbound (backend) identity (EP-07-T01/T02, README.md §20)."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from emcp_bus.downstream.identity import (
    BackendCredentialProvider,
    BackendCredentialUnavailableError,
    TokenExchangeClient,
    UnknownBackendError,
)
from emcp_bus.downstream.models import BackendConfig


def test_backend_config_rejects_a_literal_secret_in_the_env_var_name_field() -> None:
    """README.md §35.5: credentials must never live inline in config."""
    with pytest.raises(ValidationError):
        BackendConfig(
            backend="sales-domain",
            url="http://127.0.0.1:8100/mcp",
            audience="sales-domain-service",
            service_account_token_env_var="eyJhbGciOiJSUzI1NiJ9.not-an-env-var-name",
        )


def test_backend_config_requires_env_var_for_service_account_mode() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(
            backend="sales-domain", url="http://127.0.0.1:8100/mcp", audience="sales-domain-service"
        )


def test_backend_config_requires_endpoint_for_token_exchange_mode() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(
            backend="sales-domain",
            url="http://127.0.0.1:8100/mcp",
            audience="sales-domain-service",
            credential_mode="token_exchange",
            token_exchange_scope="aud-sales-domain",
        )


def test_backend_config_requires_scope_for_token_exchange_mode() -> None:
    with pytest.raises(ValidationError):
        BackendConfig(
            backend="sales-domain",
            url="http://127.0.0.1:8100/mcp",
            audience="sales-domain-service",
            credential_mode="token_exchange",
            token_exchange_endpoint="https://keycloak.example/realms/emcp/protocol/openid-connect/token",
        )


async def test_credential_for_configured_backend_resolves_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "backend-secret-token")
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                service_account_token_env_var="SALES_DOMAIN_SERVICE_TOKEN",
            )
        ]
    )

    credential = await provider.credential_for("sales-domain")

    assert credential.token == "backend-secret-token"
    assert credential.audience == "sales-domain-service"


async def test_credential_differs_from_a_hypothetical_inbound_client_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property README.md §20/ADR-006 actually cares about: whatever the
    inbound MCP Client token was, the outbound credential is never it."""
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "backend-secret-token")
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                service_account_token_env_var="SALES_DOMAIN_SERVICE_TOKEN",
            )
        ]
    )
    inbound_client_token = "inbound-oidc-access-token"  # nosec -- test fixture, not a real secret

    credential = await provider.credential_for("sales-domain")

    assert credential.token != inbound_client_token
    assert credential.audience != "emcp-gateway"  # the Gateway's own inbound audience


async def test_unknown_backend_raises() -> None:
    provider = BackendCredentialProvider([])

    with pytest.raises(UnknownBackendError):
        await provider.credential_for("no-such-backend")


async def test_missing_env_var_at_call_time_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_DOMAIN_SERVICE_TOKEN", raising=False)
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                service_account_token_env_var="SALES_DOMAIN_SERVICE_TOKEN",
            )
        ]
    )

    with pytest.raises(BackendCredentialUnavailableError):
        await provider.credential_for("sales-domain")


# --- token_exchange mode (EP-07, RFC 8693) ---------------------------------

_TOKEN_EXCHANGE_CONFIG = BackendConfig(
    backend="finance-domain",
    url="http://127.0.0.1:8101/mcp",
    audience="finance-domain-service",
    credential_mode="token_exchange",
    token_exchange_endpoint="https://keycloak.example/realms/emcp/protocol/openid-connect/token",
    token_exchange_scope="aud-finance-domain-service",
)


async def test_token_exchange_mode_without_a_configured_client_fails_closed() -> None:
    """A backend declared as `token_exchange` but with no
    GATEWAY_TOKEN_EXCHANGE_CLIENT_ID/_SECRET configured (no `TokenExchangeClient`
    passed to the provider) must DENY, not silently fall back to something else."""
    provider = BackendCredentialProvider([_TOKEN_EXCHANGE_CONFIG])

    with pytest.raises(BackendCredentialUnavailableError):
        await provider.credential_for("finance-domain")


def _mock_keycloak_transport(
    *, exchanged_token: str = "exchanged-access-token", expires_in: int = 60
) -> httpx.MockTransport:
    calls: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qsl

        body = dict(parse_qsl(request.content.decode()))
        calls.append(body)
        if body["grant_type"] == "client_credentials":
            return httpx.Response(200, json={"access_token": "subject-token", "expires_in": 300})
        assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert body["subject_token"] == "subject-token"
        assert body["audience"] == "finance-domain-service"
        assert body["scope"] == "aud-finance-domain-service"
        return httpx.Response(200, json={"access_token": exchanged_token, "expires_in": expires_in})

    transport = httpx.MockTransport(handle)
    transport.calls = calls  # type: ignore[attr-defined]
    return transport


async def test_token_exchange_produces_a_token_scoped_to_the_target_backend() -> None:
    transport = _mock_keycloak_transport()
    exchange_client = TokenExchangeClient(
        "gateway-exchange-client",
        "gateway-exchange-secret",
        http_client=httpx.AsyncClient(transport=transport),
    )
    provider = BackendCredentialProvider(
        [_TOKEN_EXCHANGE_CONFIG], token_exchange_client=exchange_client
    )

    credential = await provider.credential_for("finance-domain")

    assert credential.token == "exchanged-access-token"
    assert credential.audience == "finance-domain-service"
    await exchange_client.aclose()


async def test_token_exchange_result_is_cached_until_near_expiry() -> None:
    transport = _mock_keycloak_transport(expires_in=300)
    exchange_client = TokenExchangeClient(
        "gateway-exchange-client",
        "gateway-exchange-secret",
        http_client=httpx.AsyncClient(transport=transport),
    )
    provider = BackendCredentialProvider(
        [_TOKEN_EXCHANGE_CONFIG], token_exchange_client=exchange_client
    )

    first = await provider.credential_for("finance-domain")
    second = await provider.credential_for("finance-domain")

    assert first.token == second.token == "exchanged-access-token"
    assert len(transport.calls) == 2  # type: ignore[attr-defined]  # client_credentials + exchange, once
    await exchange_client.aclose()


async def test_token_exchange_failure_fails_closed() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_request"})

    exchange_client = TokenExchangeClient(
        "gateway-exchange-client",
        "gateway-exchange-secret",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    provider = BackendCredentialProvider(
        [_TOKEN_EXCHANGE_CONFIG], token_exchange_client=exchange_client
    )

    with pytest.raises(BackendCredentialUnavailableError):
        await provider.credential_for("finance-domain")
    await exchange_client.aclose()
