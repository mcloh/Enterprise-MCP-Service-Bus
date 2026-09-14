"""Identity Resolver / BusinessContext (EP-12-T04, ADR-022, ADR-023).

Adopts the Agent Platform OCI's `identity.yaml`/BusinessContext pattern
(ADR-022): declarative aliases mapping a channel-specific field name (e.g.
`msisdn` from an SMS channel payload) to a canonical business key (e.g.
`customer_key`), used to normalize tool-call arguments across channels.

This is purely a naming normalization for the Fabric/MCP parameter mapping
-- it is never, under any circumstance, consulted by the PDP (EP-03). That
is the explicit lesson of ADR-023 (the Hoshikawa `agent_id`-in-payload
anti-pattern): a field resolved from caller-supplied data must never
influence an authorization decision. Nothing in this module imports from
`emcp_bus.pdp` or `emcp_bus.entitlement`, and nothing should ever be added
that does.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IdentityResolverConfig(BaseModel):
    aliases: dict[str, str]
    """channel field name -> canonical business key, e.g. {"msisdn": "customer_key"}."""


class IdentityResolver:
    def __init__(self, config: IdentityResolverConfig) -> None:
        self._aliases = config.aliases

    def resolve(self, channel_payload: dict[str, Any]) -> dict[str, Any]:
        """Renames every key present in `aliases`; keys absent from
        `aliases` pass through unchanged. The result is suitable as
        `tools/call` arguments (Fabric/MCP parameter mapping) -- never as
        PDP input (see module docstring)."""
        return {self._aliases.get(key, key): value for key, value in channel_payload.items()}
