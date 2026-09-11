"""PDP decision contract (EP-03-T04).

Every response from the PDP is one of these three outcomes, never a bare
boolean -- `policy_version` and `reason_code` are mandatory so the Gateway's
audit trail (EP-08-T02) and end-to-end correlation (EP-08-T03, RF-17) always
have something to point at, and so a REQUIRE_APPROVAL is never collapsed
into ALLOW/DENY by a caller that only checks truthiness.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class PDPOutcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PDPDecision(BaseModel):
    outcome: PDPOutcome
    policy_version: str
    reason_code: str
    """Machine-readable reason, e.g. NOT_IN_ENTITLEMENT, TRANSACTION_POLICY_DENIED,
    APPROVAL_THRESHOLD_EXCEEDED, ALLOWED, PDP_UNAVAILABLE (README.md §27)."""
