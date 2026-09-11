"""PDP client (EP-03-T01/T04): wraps OPA's REST API behind the two-step
entitlement + transaction model (README.md §25).

Fail-closed by construction (README.md §38, RNF-Disponibilidade): every
method that talks to OPA either returns a `PDPDecision` or raises
`PDPUnavailableError` -- there is no code path that turns "OPA didn't
answer" into an implicit ALLOW. Callers (the Gateway, EP-05-T06) are
expected to treat `PDPUnavailableError` as DENY.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from emcp_bus.pdp.models import PDPDecision, PDPOutcome


class PDPUnavailableError(Exception):
    """OPA could not be reached or returned an unexpected response.

    Deliberately a distinct type from a `PDPDecision(outcome=DENY)`: an
    unreachable PDP is an *availability* incident (README.md §38), not a
    policy decision, and the two must never be logged/audited identically.
    """


def compute_policy_version(policy_dir: str | Path) -> str:
    """Deterministic version id for the Rego policies currently on disk.

    A SHA-256 over the sorted `*.rego` (non-test) file contents under
    `policy_dir`. This is a pragmatic stand-in for real OPA bundle revision
    tracking (which needs a bundle server) -- sufficient for the RI to prove
    `policy_version` flows end-to-end into every PDP decision and audit
    event (EP-08-T02/T03); replacing it with bundle revisions is a natural
    M2+ extension, not a contract change.
    """
    digest = hashlib.sha256()
    policy_files = sorted(
        p for p in Path(policy_dir).glob("*.rego") if not p.name.endswith("_test.rego")
    )
    for path in policy_files:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


class PDPClient:
    def __init__(self, base_url: str, policy_version: str, timeout_seconds: float = 2.0) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._policy_version = policy_version

    @property
    def policy_version(self) -> str:
        return self._policy_version

    async def aclose(self) -> None:
        await self._http.aclose()

    async def push_client_profile(self, profile_name: str, profile_data: dict[str, Any]) -> None:
        """Push a validated ClientProfile (EP-04-T01) into OPA's data document.

        Called by the Entitlement Manager (EP-04-T02) at startup/reload --
        this client never reads client profile YAML itself, only the
        already-validated dict a caller hands it.
        """
        try:
            response = await self._http.put(
                f"/v1/data/emcp/client_profiles/{profile_name}", json=profile_data
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PDPUnavailableError(
                f"Failed to push client profile {profile_name!r}: {exc}"
            ) from exc

    async def evaluate(
        self,
        *,
        client_profile: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
        customer_classification: str | None = None,
    ) -> PDPDecision:
        """Run the two-step model (README.md §25) and return one combined decision.

        Step 1 (entitlement.rego) is authoritative and short-circuits: a
        tool absent from entitlement is DENY before any argument is ever
        evaluated (Axiom 5 -- discovery/execution filtering, not argument
        policy, is the first line of defense).
        """
        entitlement_input = {"client_profile": client_profile, "tool": tool}
        entitled = await self._query_bool("/v1/data/emcp/entitlement/allow", entitlement_input)
        if not entitled:
            return PDPDecision(
                outcome=PDPOutcome.DENY,
                policy_version=self._policy_version,
                reason_code="NOT_IN_ENTITLEMENT",
            )

        transaction_input = {
            "client_profile": client_profile,
            "tool": tool,
            "arguments": arguments or {},
            "customer_classification": customer_classification,
        }
        transaction_result = await self._query("/v1/data/emcp/transaction", transaction_input)
        if not transaction_result.get("allow", False):
            return PDPDecision(
                outcome=PDPOutcome.DENY,
                policy_version=self._policy_version,
                reason_code="TRANSACTION_POLICY_DENIED",
            )
        if transaction_result.get("require_approval", False):
            return PDPDecision(
                outcome=PDPOutcome.REQUIRE_APPROVAL,
                policy_version=self._policy_version,
                reason_code="APPROVAL_THRESHOLD_EXCEEDED",
            )
        return PDPDecision(
            outcome=PDPOutcome.ALLOW,
            policy_version=self._policy_version,
            reason_code="ALLOWED",
        )

    async def _query(self, path: str, input_document: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.post(path, json={"input": input_document})
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            raise PDPUnavailableError(f"PDP query to {path} failed: {exc}") from exc
        result = body.get("result")
        if not isinstance(result, dict):
            raise PDPUnavailableError(f"PDP query to {path} returned an unexpected shape: {body!r}")
        return result

    async def _query_bool(self, path: str, input_document: dict[str, Any]) -> bool:
        try:
            response = await self._http.post(path, json={"input": input_document})
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            raise PDPUnavailableError(f"PDP query to {path} failed: {exc}") from exc
        return bool(body.get("result", False))
