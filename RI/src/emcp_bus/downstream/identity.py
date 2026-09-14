"""Outbound (backend) identity, distinct from inbound (MCP Client) identity
(EP-07-T01, README.md §20, ADR-006).

    inbound token (MCP Client -> Gateway)  !=  outbound token (Fabric -> Backend)

The Gateway authenticates the *caller*; this module answers a completely
separate question -- which credential the Fabric presents *to the backend*
-- and never answers it by handing the inbound token through unmodified
(README.md §35.6, "Token passthrough indiscriminado"). Two modes:
`service_account` resolves a static, backend-specific credential from an env
var at call time; `token_exchange` (RFC 8693 via Keycloak's Standard Token
Exchange) is implemented by `TokenExchangeClient` below -- verified
end-to-end against a real Keycloak 26.7.3 instance, 2026-09-14 (see
`downstream/models.py`'s module docstring for the exact IdP-side setup this
requires: the Gateway's own exchange client, a per-backend audience-mapper
client scope).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from emcp_bus.downstream.models import BackendConfig


class UnknownBackendError(Exception):
    pass


class BackendCredentialUnavailableError(Exception):
    """The configured credential source for a backend could not produce a token
    at call time -- a missing env var (`service_account` mode) or a failed
    RFC 8693 exchange (`token_exchange` mode).

    Distinct from `UnknownBackendError`: the backend *is* configured, but its
    credential is unavailable right now -- callers (the Gateway) must treat
    this as DENY, not as "fall back to no credential" (README.md §38).
    """


class TokenExchangeError(Exception):
    """The IdP rejected a `client_credentials` or RFC 8693 exchange call.
    Caught and re-raised as `BackendCredentialUnavailableError` by
    `BackendCredentialProvider` -- this type exists so `TokenExchangeClient`
    itself stays IdP-shaped, not Gateway-failure-policy-shaped."""


class BackendCredential(BaseModel):
    backend: str
    url: str
    token: str
    audience: str


@dataclass
class _CachedExchange:
    token: str
    expires_at: float


class TokenExchangeClient:
    """RFC 8693 token exchange against an OIDC IdP's token endpoint (Keycloak
    26.2+'s Standard Token Exchange, GA -- no preview feature flag needed).

    Two HTTP round trips per fresh exchange: (1) `client_credentials` as the
    Gateway's own exchange client, producing a subject_token; (2) exchanging
    that subject_token for one scoped to the target backend's `audience`.
    Verified empirically against a real Keycloak instance that step 2 fails
    with "Requested audience not available" unless the request also carries
    a `scope` that actually adds that audience to the token (the `audience`
    parameter alone only *restricts*, never *adds*) -- hence
    `BackendConfig.token_exchange_scope`.

    Exchanged tokens are cached per backend until shortly before their own
    `expires_in` (RFC 8693 exchanged tokens are commonly short-lived, and
    re-exchanging on every single `tools/call` would be both wasteful and
    slow); a cache hit costs zero HTTP round trips.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        expiry_margin_seconds: float = 5.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client or httpx.AsyncClient()
        self._expiry_margin_seconds = expiry_margin_seconds
        self._cache: dict[str, _CachedExchange] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def exchange(
        self, *, token_endpoint: str, backend: str, audience: str, scope: str
    ) -> str:
        now = time.monotonic()
        cached = self._cache.get(backend)
        if cached is not None and cached.expires_at > now:
            return cached.token

        subject_token = await self._client_credentials(token_endpoint)
        token, expires_in = await self._exchange(token_endpoint, subject_token, audience, scope)
        self._cache[backend] = _CachedExchange(
            token=token, expires_at=now + max(expires_in - self._expiry_margin_seconds, 0.0)
        )
        return token

    async def _client_credentials(self, token_endpoint: str) -> str:
        try:
            response = await self._http.post(
                token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TokenExchangeError(
                f"Failed to obtain the exchange client's own subject token from "
                f"{token_endpoint}: {exc}"
            ) from exc
        access_token: str = response.json()["access_token"]
        return access_token

    async def _exchange(
        self, token_endpoint: str, subject_token: str, audience: str, scope: str
    ) -> tuple[str, int]:
        try:
            response = await self._http.post(
                token_endpoint,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": subject_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "audience": audience,
                    "scope": scope,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TokenExchangeError(
                f"RFC 8693 token exchange for audience {audience!r} (scope {scope!r}) "
                f"at {token_endpoint} failed: {exc}"
            ) from exc
        body = response.json()
        return body["access_token"], int(body.get("expires_in", 60))


class BackendCredentialProvider:
    def __init__(
        self,
        backend_configs: list[BackendConfig],
        *,
        token_exchange_client: TokenExchangeClient | None = None,
    ) -> None:
        self._configs = {config.backend: config for config in backend_configs}
        self._token_exchange_client = token_exchange_client

    async def credential_for(self, backend: str) -> BackendCredential:
        config = self._configs.get(backend)
        if config is None:
            raise UnknownBackendError(backend)

        if config.credential_mode == "token_exchange":
            return await self._credential_via_token_exchange(backend, config)

        assert config.service_account_token_env_var is not None  # enforced by BackendConfig
        token = os.environ.get(config.service_account_token_env_var)
        if not token:
            raise BackendCredentialUnavailableError(
                f"Environment variable {config.service_account_token_env_var!r} for backend "
                f"{backend!r} is not set"
            )
        return BackendCredential(
            backend=backend, url=config.url, token=token, audience=config.audience
        )

    async def _credential_via_token_exchange(
        self, backend: str, config: BackendConfig
    ) -> BackendCredential:
        if self._token_exchange_client is None:
            raise BackendCredentialUnavailableError(
                f"Backend {backend!r} is configured for credential_mode='token_exchange' but "
                "no TokenExchangeClient is available (GATEWAY_TOKEN_EXCHANGE_CLIENT_ID/"
                "_SECRET unset) -- see emcp_bus.downstream.identity module docstring."
            )
        assert config.token_exchange_endpoint is not None  # enforced by BackendConfig
        assert config.token_exchange_scope is not None  # enforced by BackendConfig
        try:
            token = await self._token_exchange_client.exchange(
                token_endpoint=config.token_exchange_endpoint,
                backend=backend,
                audience=config.audience,
                scope=config.token_exchange_scope,
            )
        except TokenExchangeError as exc:
            raise BackendCredentialUnavailableError(str(exc)) from exc
        return BackendCredential(
            backend=backend, url=config.url, token=token, audience=config.audience
        )

    def url_for(self, backend: str) -> str:
        config = self._configs.get(backend)
        if config is None:
            raise UnknownBackendError(backend)
        return config.url
