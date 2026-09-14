"""Outbound (backend) identity, distinct from inbound (MCP Client) identity
(EP-07-T01, README.md §20, ADR-006).

    inbound token (MCP Client -> Gateway)  !=  outbound token (Fabric -> Backend)

The Gateway authenticates the *caller*; this module answers a completely
separate question -- which credential the Fabric presents *to the backend*
-- and never answers it by handing the inbound token through unmodified
(README.md §35.6, "Token passthrough indiscriminado"). `service_account`
mode resolves a static, backend-specific credential from an env var at call
time; `token_exchange` (RFC 8693) is a documented, unimplemented extension
(see `BackendConfig`).
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from emcp_bus.downstream.models import BackendConfig


class UnknownBackendError(Exception):
    pass


class BackendCredentialUnavailableError(Exception):
    """The configured env var for a backend's service-account token is unset.

    Distinct from `UnknownBackendError`: the backend *is* configured, but
    its credential is missing at runtime -- callers (the Gateway) must
    treat this as DENY, not as "fall back to no credential" (README.md §38).
    """


class BackendCredential(BaseModel):
    backend: str
    url: str
    token: str
    audience: str


class BackendCredentialProvider:
    def __init__(self, backend_configs: list[BackendConfig]) -> None:
        self._configs = {config.backend: config for config in backend_configs}

    def credential_for(self, backend: str) -> BackendCredential:
        config = self._configs.get(backend)
        if config is None:
            raise UnknownBackendError(backend)

        if config.credential_mode == "token_exchange":
            raise NotImplementedError(
                f"credential_mode='token_exchange' for backend {backend!r} is a documented "
                "extension point (RFC 8693 via an OIDC IdP), not implemented in this RI -- "
                "see BackendConfig docstring."
            )

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

    def url_for(self, backend: str) -> str:
        config = self._configs.get(backend)
        if config is None:
            raise UnknownBackendError(backend)
        return config.url
