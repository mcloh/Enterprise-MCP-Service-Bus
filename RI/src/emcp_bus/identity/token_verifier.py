"""Adapts `TokenValidator` (EP-01-T03) to the `mcp` SDK's own `TokenVerifier`
protocol, so the Gateway can use the SDK's built-in bearer-auth middleware
(`AuthenticationMiddleware` + `AuthContextMiddleware`) instead of parsing the
`Authorization` header by hand.
"""

from __future__ import annotations

import asyncio

from mcp.server.auth.provider import AccessToken

from emcp_bus.identity.authn import AuthenticationError, TokenValidator


class MCPTokenVerifier:
    def __init__(self, token_validator: TokenValidator, resource: str) -> None:
        self._token_validator = token_validator
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        """Returns `None` on any validation failure -- the SDK's bearer-auth
        middleware treats that as "no authenticated user", never as an
        exception to swallow-and-allow. `TokenValidator.validate` does a
        blocking JWKS fetch/signature check (PyJWT), so it runs off the
        event loop thread."""
        try:
            authenticated = await asyncio.to_thread(self._token_validator.validate, token)
        except AuthenticationError:
            return None

        return AccessToken(
            token=token,
            client_id=authenticated.client_id,
            scopes=[],
            expires_at=authenticated.expires_at,
            resource=self._resource,
        )
