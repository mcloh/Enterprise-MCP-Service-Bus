"""MCP Client registration schema (EP-01-T02, README.md §6.3, §19).

Maps an authenticated OAuth2 client identity (the `client_id`/`azp` claim a
validated access token carries -- see EP-01-T03) to exactly one client
profile (EP-04). This indirection is what lets `docs/RI-PLANNING.md`'s §18
rule ("share a client only if all sharing agents can legitimately carry the
same ceiling") be expressed as data instead of code: two client_ids pointing
at the same profile are an explicit, auditable sharing decision.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClientRegistration(BaseModel):
    client_id: str
    """OAuth2 client_id as issued by the Identity Provider (Keycloak, EP-01-T01).

    This is the identity the Gateway trusts (from a verified token's `azp`
    claim, EP-01-T03) -- never a value read from the MCP request body or
    from `clientInfo` (README.md §5, "Observação crítica sobre clientInfo").
    """

    profile: str
    """Name of the ClientProfile (EP-04) this client_id resolves to."""

    environment: Literal["dev", "ci", "production"] = "production"
    description: str | None = None
