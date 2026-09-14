"""Shared-client lint (EP-01-T05, README.md §18/§35).

The anti-pattern this closes: two distinct agents registered against the
*same* underlying MCP Client (`client_id` -- the same Identity Provider
client/secret) but pointing at *different* client profiles. Sharing one
`client_id` across agents is only ever safe when every agent that shares it
would legitimately carry the same MaximumEntitlement ceiling (README.md
§18); if their registrations disagree on `profile`, one of two agents is
either over- or under-entitled relative to what its own registration
declares, and which one wins is just whichever YAML `load_yaml_models`
happens to process last (`EntitlementManager.load_registrations` keys
registrations by `client_id` in a plain dict) -- a silent, unaudited
authorization change, not a deliberate sharing decision.
"""

from __future__ import annotations

from collections import defaultdict

from emcp_bus.identity.models import ClientRegistration


class SharedClientLintError(Exception):
    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


def find_shared_client_violations(registrations: list[ClientRegistration]) -> list[str]:
    profiles_by_client: dict[str, set[str]] = defaultdict(set)
    for registration in registrations:
        profiles_by_client[registration.client_id].add(registration.profile)

    return [
        f"client_id {client_id!r} is registered against more than one profile: {sorted(profiles)} "
        "(README.md §18/§35: agents sharing an MCP Client must resolve to the same profile)"
        for client_id, profiles in sorted(profiles_by_client.items())
        if len(profiles) > 1
    ]


def assert_no_shared_client_violations(registrations: list[ClientRegistration]) -> None:
    violations = find_shared_client_violations(registrations)
    if violations:
        raise SharedClientLintError(violations)
