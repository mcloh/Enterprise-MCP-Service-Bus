"""Shared-client lint (EP-01-T05, README.md §18/§35)."""

from __future__ import annotations

import pytest

from emcp_bus.identity.models import ClientRegistration
from emcp_bus.identity.shared_client_lint import (
    SharedClientLintError,
    assert_no_shared_client_violations,
    find_shared_client_violations,
)


def test_distinct_client_ids_are_never_a_violation() -> None:
    registrations = [
        ClientRegistration(client_id="sales-read-agent", profile="Sales.Read"),
        ClientRegistration(client_id="sales-write-agent", profile="Sales.Write"),
    ]

    assert find_shared_client_violations(registrations) == []


def test_same_client_id_and_same_profile_is_not_a_violation() -> None:
    """Sharing is fine when both registrations agree on the profile -- this
    is the legitimate case README.md §18 describes."""
    registrations = [
        ClientRegistration(client_id="shared-agent", profile="Sales.Read"),
        ClientRegistration(client_id="shared-agent", profile="Sales.Read"),
    ]

    assert find_shared_client_violations(registrations) == []


def test_same_client_id_with_different_profiles_is_a_violation() -> None:
    registrations = [
        ClientRegistration(client_id="shared-agent", profile="Sales.Read"),
        ClientRegistration(client_id="shared-agent", profile="Finance.Payments"),
    ]

    violations = find_shared_client_violations(registrations)

    assert len(violations) == 1
    assert "shared-agent" in violations[0]


def test_assert_raises_with_all_violations_when_present() -> None:
    registrations = [
        ClientRegistration(client_id="shared-agent", profile="Sales.Read"),
        ClientRegistration(client_id="shared-agent", profile="Finance.Payments"),
    ]

    with pytest.raises(SharedClientLintError):
        assert_no_shared_client_violations(registrations)


def test_assert_does_not_raise_when_clean() -> None:
    registrations = [ClientRegistration(client_id="sales-read-agent", profile="Sales.Read")]

    assert_no_shared_client_violations(registrations)  # must not raise


def test_the_real_seed_client_registrations_have_no_violations() -> None:
    """The RI's own config/clients/*.yaml must pass its own lint."""
    from pathlib import Path

    from emcp_bus.common.config import load_yaml_models

    repo_root = Path(__file__).parents[2]
    registrations = load_yaml_models(repo_root / "config" / "clients", ClientRegistration)

    assert_no_shared_client_violations(registrations)  # must not raise
