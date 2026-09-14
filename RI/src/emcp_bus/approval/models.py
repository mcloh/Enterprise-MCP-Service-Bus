"""Approval request contract (EP-14-T01, README.md §26).

Out-of-band, bound to the *exact* operation it was requested for (not just
the tool name), with an expiry and single-use semantics -- so an approval
granted for one call can never be replayed against a different one (same
tool, different arguments) or reused twice (README.md §46, "approval
replay").
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def compute_operation_hash(*, client_profile: str, tool: str, arguments: dict[str, Any]) -> str:
    """Binds an approval to one exact (client_profile, tool, arguments) triple.

    Canonical JSON (sorted keys) so the same logical call always hashes the
    same way regardless of dict insertion order.
    """
    canonical = json.dumps(
        {"client_profile": client_profile, "tool": tool, "arguments": arguments},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalRequest(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_hash: str
    client_profile: str
    tool: str
    arguments_summary: dict[str, Any]
    """A copy of the relevant arguments for an approver to review -- README.md
    §26 ("com resumo dos argumentos relevantes"). Not redacted in this RI;
    a production deployment would apply the same PII-minimization rules as
    audit logging (README.md §27)."""

    reason_code: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    status: Literal["pending", "granted", "denied", "consumed"] = "pending"

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at
