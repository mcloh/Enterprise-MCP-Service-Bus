"""Backend credential config schema (EP-07-T02, README.md §20).

One entry per backend the Fabric calls, declaring *how* the Gateway obtains
an outbound credential for it -- never the credential's value. The RI
implements `service_account` (a static credential resolved from an env var
at call time); `token_exchange` (RFC 8693, e.g. via Keycloak) is modeled as
a distinct, documented mode but not implemented in this milestone -- see
`emcp_bus.downstream.identity.BackendCredentialProvider`.
"""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, field_validator, model_validator

_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class BackendConfig(BaseModel):
    backend: str
    """Adapter/service id, matching `CapabilityManifest.backend.service` (EP-02-T01)."""

    url: str
    """Where the Fabric router (EP-06-T01) connects to reach this backend --
    an MCP streamable-http endpoint for `backend.type == "mcp"`, or a REST
    base URL for `"rest"` (EP-06-T04). Not a secret, so unlike the credential
    fields below it may be a literal value, though it commonly uses
    `${VAR}` too since it differs between `make dev` (127.0.0.1) and Docker
    (the compose service DNS name)."""

    audience: str
    """The outbound token's audience -- deliberately never equal to the Gateway's
    own inbound `OIDC_AUDIENCE` (README.md §20: inbound and outbound authorization
    are distinct relations)."""

    credential_mode: Literal["service_account", "token_exchange"] = "service_account"

    service_account_token_env_var: str | None = None
    """Name (not value) of the environment variable holding the backend's
    static credential. Required when `credential_mode == "service_account"`."""

    token_exchange_endpoint: str | None = None
    """RFC 8693 token endpoint URL. Documented extension point, not yet
    implemented -- see module docstring."""

    @field_validator("service_account_token_env_var")
    @classmethod
    def _looks_like_an_env_var_name_not_a_secret(cls, value: str | None) -> str | None:
        if value is not None and not _ENV_VAR_NAME_PATTERN.match(value):
            raise ValueError(
                f"{value!r} does not look like an environment variable name "
                "(expected e.g. 'SALES_DOMAIN_SERVICE_TOKEN') -- this field must "
                "never hold a literal secret value (README.md §35.5)"
            )
        return value

    @model_validator(mode="after")
    def _required_field_matches_credential_mode(self) -> Self:
        if self.credential_mode == "service_account" and not self.service_account_token_env_var:
            raise ValueError(
                "service_account_token_env_var is required for credential_mode='service_account'"
            )
        if self.credential_mode == "token_exchange" and not self.token_exchange_endpoint:
            raise ValueError(
                "token_exchange_endpoint is required when credential_mode == 'token_exchange'"
            )
        return self
