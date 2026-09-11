"""OAuth2/OIDC access token validation (EP-01-T03, README.md §5, §19, §20).

Validates a bearer token against the Identity Provider's JWKS (Keycloak,
EP-01-T01, in production; any standards-compliant OIDC IdP works, since this
speaks the standard, not a Keycloak-specific protocol) -- signature,
expiry, issuer and audience. The verified `azp`/`client_id` claim is the
*only* source of client identity this module trusts; nothing about
`clientInfo` or any other agent-declared field is ever consulted here
(README.md §5, "Observação crítica sobre clientInfo", Axiom 2).
"""

from __future__ import annotations

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel


class AuthenticationError(Exception):
    """Token missing/malformed/expired/wrong audience-issuer/bad signature.

    Callers (the Gateway, EP-05-T02/T04) must treat this identically to
    DENY -- fail closed (README.md §38), never fall back to an unauthenticated
    or agent-declared identity.
    """


class AuthenticatedClient(BaseModel):
    client_id: str
    """From the token's `azp` (OIDC 'authorized party') or `client_id` claim --
    never from clientInfo or any other unauthenticated, agent-controlled field."""

    issuer: str
    expires_at: int


class TokenValidator:
    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 5,
    ) -> None:
        self._jwks_client = PyJWKClient(jwks_url)
        self._issuer = issuer
        self._audience = audience
        self._leeway_seconds = leeway_seconds

    def validate(self, token: str) -> AuthenticatedClient:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(str(exc)) from exc

        client_id = claims.get("azp") or claims.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            raise AuthenticationError("Token has neither a usable 'azp' nor 'client_id' claim")

        return AuthenticatedClient(
            client_id=client_id,
            issuer=str(claims["iss"]),
            expires_at=int(claims["exp"]),
        )
