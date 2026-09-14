"""Outbound (backend) identity (EP-07-T01/T02, README.md §20)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from emcp_bus.downstream.identity import (
    BackendCredentialProvider,
    BackendCredentialUnavailableError,
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
        )


def test_credential_for_configured_backend_resolves_from_env(
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

    credential = provider.credential_for("sales-domain")

    assert credential.token == "backend-secret-token"
    assert credential.audience == "sales-domain-service"


def test_credential_differs_from_a_hypothetical_inbound_client_token(
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

    credential = provider.credential_for("sales-domain")

    assert credential.token != inbound_client_token
    assert credential.audience != "emcp-gateway"  # the Gateway's own inbound audience


def test_unknown_backend_raises() -> None:
    provider = BackendCredentialProvider([])

    with pytest.raises(UnknownBackendError):
        provider.credential_for("no-such-backend")


def test_missing_env_var_at_call_time_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
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
        provider.credential_for("sales-domain")


def test_token_exchange_mode_is_a_documented_but_unimplemented_extension() -> None:
    provider = BackendCredentialProvider(
        [
            BackendConfig(
                backend="sales-domain",
                url="http://127.0.0.1:8100/mcp",
                audience="sales-domain-service",
                credential_mode="token_exchange",
                token_exchange_endpoint="https://keycloak.example/realms/emcp/token",
            )
        ]
    )

    with pytest.raises(NotImplementedError):
        provider.credential_for("sales-domain")
