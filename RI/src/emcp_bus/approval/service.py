"""Approval service (EP-14-T02, README.md §26).

Gates a `REQUIRE_APPROVAL` PDP decision (EP-03-T04): the Gateway calls
`check_and_consume` for every attempt of an operation that needs approval; a
human approver (CLI, API, or a future Orchestrator human-in-the-loop node,
EP-11-T05) calls `request`/`grant`/`deny` out-of-band. Approval is never
implicit -- a REQUIRE_APPROVAL attempt with no matching grant is denied, not
queued-and-allowed.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from emcp_bus.approval.models import ApprovalRequest, compute_operation_hash
from emcp_bus.audit.events import approval_granted
from emcp_bus.audit.sink import AuditSink


class ApprovalNotFoundError(Exception):
    pass


class ApprovalService:
    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._audit_sink = audit_sink
        # EP-15-T04 ("approval replay" under concurrency): `check_and_consume`'s
        # check-then-set (read `.status`, then write it) is not a single
        # bytecode op, so without this lock two real OS threads racing the
        # same granted approval could both observe "granted" before either
        # writes "consumed" -- a double-spend of a single-use grant. Plain
        # `threading.Lock`, not `asyncio.Lock`: this service is called from
        # sync code paths (the Gateway's request handler) that may run under
        # a thread pool, not only from a single asyncio event loop.
        self._lock = threading.Lock()

    def request(
        self,
        *,
        client_profile: str,
        tool: str,
        arguments: dict[str, Any],
        reason_code: str,
        ttl_seconds: int = 300,
    ) -> ApprovalRequest:
        """Create (or return the existing pending one for) an approval request
        for this exact operation -- repeated attempts of the same call while
        one is pending do not spawn duplicate requests for an approver to
        wade through."""
        operation_hash = compute_operation_hash(
            client_profile=client_profile, tool=tool, arguments=arguments
        )
        existing = self._pending_for_operation(operation_hash)
        if existing is not None:
            return existing

        approval = ApprovalRequest(
            operation_hash=operation_hash,
            client_profile=client_profile,
            tool=tool,
            arguments_summary=arguments,
            reason_code=reason_code,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self._requests[approval.approval_id] = approval
        return approval

    def grant(self, approval_id: str) -> None:
        approval = self._get(approval_id)
        approval.status = "granted"
        if self._audit_sink is not None:
            self._audit_sink.emit(
                approval_granted(
                    approval_id=approval.approval_id,
                    client_profile=approval.client_profile,
                    tool=approval.tool,
                )
            )

    def deny(self, approval_id: str) -> None:
        approval = self._get(approval_id)
        approval.status = "denied"

    def check_and_consume(
        self, *, client_profile: str, tool: str, arguments: dict[str, Any]
    ) -> bool:
        """True exactly once for a matching, granted, unexpired approval.

        Single-use (README.md §46, "approval replay"): a granted approval
        that passes this check is immediately marked `consumed` and can
        never satisfy a second attempt, even of the identical operation.
        """
        operation_hash = compute_operation_hash(
            client_profile=client_profile, tool=tool, arguments=arguments
        )
        with self._lock:
            for approval in self._requests.values():
                if (
                    approval.operation_hash == operation_hash
                    and approval.status == "granted"
                    and not approval.is_expired()
                ):
                    approval.status = "consumed"
                    return True
            return False

    def _pending_for_operation(self, operation_hash: str) -> ApprovalRequest | None:
        for approval in self._requests.values():
            if (
                approval.operation_hash == operation_hash
                and approval.status == "pending"
                and not approval.is_expired()
            ):
                return approval
        return None

    def _get(self, approval_id: str) -> ApprovalRequest:
        approval = self._requests.get(approval_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        return approval
