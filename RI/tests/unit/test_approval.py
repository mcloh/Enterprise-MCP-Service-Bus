"""Approval workflow (EP-14-T01/T02/T03, README.md §26, §46 approval replay)."""

from __future__ import annotations

import pytest

from emcp_bus.approval.models import compute_operation_hash
from emcp_bus.approval.service import ApprovalNotFoundError, ApprovalService


def test_operation_hash_is_stable_regardless_of_argument_order() -> None:
    a = compute_operation_hash(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000, "currency": "BRL"},
    )
    b = compute_operation_hash(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"currency": "BRL", "amount": 50_000},
    )
    assert a == b


def test_operation_hash_differs_for_different_arguments() -> None:
    """A grant for one exact call must never satisfy a different one (README.md §26)."""
    a = compute_operation_hash(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000},
    )
    b = compute_operation_hash(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 999_999},
    )
    assert a != b


def test_unapproved_operation_is_not_consumed() -> None:
    service = ApprovalService()

    consumed = service.check_and_consume(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000},
    )

    assert consumed is False


def test_request_then_grant_then_consume_succeeds_exactly_once() -> None:
    service = ApprovalService()
    arguments = {"amount": 50_000}
    request = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments=arguments,
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )

    service.grant(request.approval_id)

    assert (
        service.check_and_consume(
            client_profile="Finance.Payments", tool="finance.payment.execute", arguments=arguments
        )
        is True
    )
    # README.md §46 "approval replay": the second attempt of the *same* call
    # must not be satisfied by an already-consumed grant.
    assert (
        service.check_and_consume(
            client_profile="Finance.Payments", tool="finance.payment.execute", arguments=arguments
        )
        is False
    )


def test_denied_request_is_never_consumable() -> None:
    service = ApprovalService()
    arguments = {"amount": 50_000}
    request = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments=arguments,
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )

    service.deny(request.approval_id)

    assert (
        service.check_and_consume(
            client_profile="Finance.Payments", tool="finance.payment.execute", arguments=arguments
        )
        is False
    )


def test_grant_does_not_satisfy_a_different_operation() -> None:
    """Granting approval for one amount must not let a *different* amount through."""
    service = ApprovalService()
    request = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000},
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )
    service.grant(request.approval_id)

    consumed = service.check_and_consume(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 999_999},  # different operation entirely
    )

    assert consumed is False


def test_expired_grant_is_not_consumable() -> None:
    service = ApprovalService()
    arguments = {"amount": 50_000}
    request = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments=arguments,
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
        ttl_seconds=0,
    )
    service.grant(request.approval_id)

    consumed = service.check_and_consume(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments=arguments,
    )

    assert consumed is False


def test_repeated_pending_requests_for_the_same_operation_do_not_duplicate() -> None:
    service = ApprovalService()
    first = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000},
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )
    second = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments={"amount": 50_000},
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )

    assert first.approval_id == second.approval_id


def test_grant_unknown_approval_id_raises() -> None:
    service = ApprovalService()

    with pytest.raises(ApprovalNotFoundError):
        service.grant("no-such-id")
