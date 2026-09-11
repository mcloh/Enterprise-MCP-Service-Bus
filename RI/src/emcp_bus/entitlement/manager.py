"""Entitlement Manager (EP-04-T02/T03/T04, README.md §6.9).

Resolves `MaximumEntitlement(client)` by combining an authenticated
client_id (never a value the agent/prompt could influence -- EP-01-T03) with
its registered `ClientProfile` (EP-04-T01), and keeps that resolution
versioned, cacheable and revocable (RF-08, RF-12). This module is the
*only* authority for `MaximumEntitlement` in the RI: it does not rank
relevance, does not compute NBA, and does not trust anything the LLM
declared (README.md §6.9, Axiom 2).
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from emcp_bus.common.models import RiskTier
from emcp_bus.entitlement.models import ClientProfile
from emcp_bus.identity.models import ClientRegistration
from emcp_bus.pdp.client import PDPClient


class UnknownClientError(Exception):
    """`client_id` has no registration, or its registration points at an unknown
    profile. Callers (the Gateway) must treat this identically to DENY --
    never as "grant the default/broadest profile"."""


class ResolvedEntitlement(BaseModel):
    client_id: str
    profile_name: str
    entitlement_version: str
    """Changes whenever the client profile OR the PDP policies change (EP-04-T04) --
    a Gateway cache keyed partly on this value self-invalidates on either (EP-05-T03)."""
    allowed_tools: frozenset[str]
    risk_ceiling: RiskTier
    provenance: str
    """Which rule produced this entitlement -- trivial in the RI (one client
    profile, no additional dynamic rule composition yet), but the field
    exists so a richer Entitlement Manager can report it without a contract
    change (README.md §6.9, "manter provenance")."""

    model_config = {"frozen": True}


class EntitlementManager:
    def __init__(self, pdp_client: PDPClient) -> None:
        self._pdp = pdp_client
        self._registrations: dict[str, ClientRegistration] = {}
        self._profiles: dict[str, ClientProfile] = {}
        self._cache: dict[str, ResolvedEntitlement] = {}

    def load_registrations(self, registrations: list[ClientRegistration]) -> None:
        self._registrations = {r.client_id: r for r in registrations}

    def load_profiles(self, profiles: list[ClientProfile]) -> None:
        self._profiles = {p.name: p for p in profiles}

    async def sync_profiles_to_pdp(self) -> None:
        """Push every loaded client profile into the PDP's data document.

        Must run (and complete) before the Gateway starts accepting
        `tools/list`/`tools/call` -- a profile the PDP has never seen
        resolves every tool to DENY, which is the correct fail-closed
        behavior (README.md §38), never a reason to skip the sync.
        """
        for profile in self._profiles.values():
            # `exclude_none`: Rego's `not X` only negates an *undefined* or
            # literal-`false` X -- a pushed `null` is a defined value, so
            # `not profile.restrictions.max_transaction_value` would NOT
            # treat an explicit `null` as "no restriction" the way it treats
            # a genuinely absent key. Dropping None fields keeps "unset"
            # meaning "undefined in Rego" (see config/policies/transaction.rego).
            await self._pdp.push_client_profile(
                profile.name,
                profile.model_dump(mode="json", exclude={"name"}, exclude_none=True),
            )

    def resolve(self, client_id: str) -> ResolvedEntitlement:
        """Resolve and cache `MaximumEntitlement(client_id)`.

        Cache lookups are keyed on `client_id` only, but `entitlement_version`
        inside the cached value is computed from the *current* profile
        content and PDP policy_version every time -- so a stale cache entry
        is always self-describing (a caller comparing versions can tell it's
        stale) even though this method does not itself re-fetch policy state
        from OPA on every call (see `revoke_client`/`revoke_profile` for the
        actual invalidation triggers, EP-04-T03).
        """
        registration = self._registrations.get(client_id)
        if registration is None:
            raise UnknownClientError(f"No ClientRegistration for client_id={client_id!r}")

        profile = self._profiles.get(registration.profile)
        if profile is None:
            raise UnknownClientError(
                f"ClientRegistration for {client_id!r} references unknown profile "
                f"{registration.profile!r}"
            )

        resolved = ResolvedEntitlement(
            client_id=client_id,
            profile_name=profile.name,
            entitlement_version=self._compute_version(profile),
            allowed_tools=frozenset(profile.allowed_tools),
            risk_ceiling=profile.risk_ceiling,
            provenance=f"client_profile:{profile.name}",
        )
        self._cache[client_id] = resolved
        return resolved

    def cached(self, client_id: str) -> ResolvedEntitlement | None:
        return self._cache.get(client_id)

    def revoke_client(self, client_id: str) -> None:
        """Immediately invalidate one client's entitlement (RF-08).

        The *next* `resolve()` for this client_id will raise
        `UnknownClientError` until/unless it is re-registered -- there is no
        grace period and no fallback to a cached value.
        """
        self._registrations.pop(client_id, None)
        self._cache.pop(client_id, None)

    def revoke_profile(self, profile_name: str) -> None:
        """Invalidate the cache for every client currently on `profile_name`.

        Used when a profile itself changes (not just one client) --
        `policy_changed` in the audit taxonomy (README.md §27). Does not
        remove the profile or its registrations; the next `resolve()` call
        recomputes against whatever profile is loaded now.
        """
        stale_client_ids = [
            client_id
            for client_id, resolved in self._cache.items()
            if resolved.profile_name == profile_name
        ]
        for client_id in stale_client_ids:
            del self._cache[client_id]

    def _compute_version(self, profile: ClientProfile) -> str:
        digest = hashlib.sha256()
        digest.update(self._pdp.policy_version.encode("utf-8"))
        digest.update(profile.model_dump_json().encode("utf-8"))
        return digest.hexdigest()[:12]
