"""Adversarial protocol/identity scenarios (EP-15-T04, README.md §46).

Of the scenarios this task's backlog entry names -- replay, stolen token,
expired token, wrong-audience token, header/body mismatch, shared-cache
poisoning, entitlement race condition, approval replay -- several already
have real, live coverage elsewhere and are not duplicated here:

- **expired token** / **wrong-audience token** / **stolen token** (forged
  signature): `tests/e2e/test_governed_gateway.py::test_expired_token_is_denied`
  / `test_wrong_audience_token_is_denied` / `test_forged_signature_token_is_denied`,
  plus the unit-level equivalents in `tests/unit/test_authn.py`. A "stolen"
  but genuinely *valid* token's containment (it cannot exceed its own
  client's entitlement even though it authenticates successfully) is
  README.md §45 Teste 10, proven live against real Docker in
  `tests/e2e/test_security_acceptance.py::test_teste10_client_compromise_containment_against_real_docker`.
- **approval replay** (sequential):
  `tests/e2e/test_governed_gateway.py::test_full_approval_cycle_grant_then_execute_then_replay_denied`
  (and its Finance-domain twin). This file adds the *concurrent* variant
  below, a genuinely different failure mode (a race on a single-use grant,
  not a second sequential attempt).
- **shared-cache poisoning** (cross-client): README.md §45 Teste 5,
  `tests/e2e/test_governed_gateway.py::test_sales_client_tools_list_never_includes_finance_tools`
  and the real-Docker `cache_scope="private"` assertion in
  `test_security_acceptance.py::test_teste5_cache_isolation_against_real_docker`.
  This file adds the *revocation* angle below (no cache ever serves a
  *now-stale* response either, not just never a cross-client one) --
  closing the live-Gateway gap `test_security_acceptance.py` disclosed for
  Teste 6 ("policy revocation", no HTTP endpoint exists to trigger one).

New here: header/body mismatch, replay (with an honest disclosed gap),
live policy revocation, entitlement race condition, approval replay under
concurrency, and bulk exfiltration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx

from emcp_bus.audit.sink import InMemoryAuditSink
from tests.e2e.conftest import gateway_url, run_against_gateway

SALES_READ_CLIENT_ID = "sales-read-agent"
SALES_WRITE_CLIENT_ID = "sales-write-agent"


async def test_mismatched_mcp_method_header_is_rejected_before_authentication(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """EP-05-T08/SEP-2243: an `Mcp-Method` header that disagrees with the
    JSON-RPC body's own `method` is rejected by `CanonicalRequestGate`
    before the request reaches auth or any handler -- proven here with a
    raw HTTP POST (not `ClientSession`, which always sends a consistent
    pair) carrying an otherwise-valid bearer token."""
    token = sign_token(SALES_READ_CLIENT_ID)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            gateway_url(),
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "mcp-method": "tools/call",  # deliberately disagrees with body.method above
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "header_body_mismatch"


async def test_a_byte_identical_request_replayed_twice_is_independently_correlated(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §46 "replay": this RI has no per-request nonce/anti-replay
    mechanism -- a captured, still-valid bearer token can carry the
    identical `tools/call` twice, and both succeed. This is a real, honest
    gap (mitigated only by short-lived tokens, `credential_policy.short_lived`
    in every seed `ClientProfile`, README.md §41), not something this test
    pretends to close. What it does prove is the compensating control
    README.md §27 asks for: even a byte-identical replay is never conflated
    with the original in the audit trail -- each attempt gets its own
    `decision_id` (`emcp_bus.audit.correlation.new_decision_id()`), so the
    two remain distinguishable after the fact."""
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(SALES_READ_CLIENT_ID)
    sink = InMemoryAuditSink()
    gateway_module.get_current_state().audit_sink = sink

    arguments = {"customer_id": "cust-001"}
    first = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", arguments), token=token
    )
    second = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", arguments), token=token
    )

    assert first.is_error is not True
    assert second.is_error is not True
    allowed_events = [e for e in sink.events if e.event_type == "tool_call_allowed"]
    assert len(allowed_events) == 2
    assert allowed_events[0].decision_id != allowed_events[1].decision_id


async def test_live_policy_revocation_takes_effect_on_the_very_next_request(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 6 ("policy revocation"), live against a running
    Gateway. `test_security_acceptance.py`'s module docstring disclosed
    that this RI has no HTTP-exposed revoke endpoint to drive this test
    through a real client request -- this exercises the exact same
    underlying primitives (`EntitlementManager.load_profiles`/
    `revoke_profile` + `PDPClient.push_client_profile`) such an endpoint
    would call, live against the same running Gateway/OPA a real client is
    talking to, rather than at the unit level (`tests/unit/test_entitlement_manager.py`)."""
    import emcp_bus.gateway.server as gateway_module
    from emcp_bus.common.config import load_yaml_models
    from emcp_bus.entitlement.models import ClientProfile
    from emcp_bus.gateway.server import GatewayConfig

    token = sign_token(SALES_WRITE_CLIENT_ID)

    baseline = await run_against_gateway(
        lambda session: session.call_tool(
            "sales.quote.create", {"customer_id": "cust-001", "amount": 100.0, "region": "BR-SP"}
        ),
        token=token,
    )
    assert baseline.is_error is not True

    config = GatewayConfig.from_env()
    profiles = {p.name: p for p in load_yaml_models(config.profiles_dir, ClientProfile)}
    reduced = profiles["Sales.Write"].model_copy(
        update={
            "allowed_tools": [
                t for t in profiles["Sales.Write"].allowed_tools if t != "sales.quote.create"
            ]
        }
    )
    profiles["Sales.Write"] = reduced

    state = gateway_module.get_current_state()
    state.entitlement_manager.load_profiles(list(profiles.values()))
    state.entitlement_manager.revoke_profile("Sales.Write")
    await state.pdp.push_client_profile(
        "Sales.Write", reduced.model_dump(mode="json", exclude={"name"}, exclude_none=True)
    )

    after_revoke = await run_against_gateway(
        lambda session: session.call_tool(
            "sales.quote.create", {"customer_id": "cust-001", "amount": 100.0, "region": "BR-SP"}
        ),
        token=token,
    )
    assert after_revoke.is_error is True

    catalog = await run_against_gateway(lambda session: session.list_tools(), token=token)
    assert "sales.quote.create" not in {t.name for t in catalog.tools}


async def test_entitlement_revocation_mid_flight_never_leaves_an_inconsistent_result(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §46 "entitlement race condition": a batch of in-flight
    calls overlapping a concurrent `revoke_client` must never crash or
    return a malformed/half-applied result -- every one resolves cleanly to
    either ALLOW or DENY, and any call that starts strictly after the
    revoke completes is deterministically denied. (`EntitlementManager`'s
    mutations are plain synchronous dict writes -- see its module docstring
    -- so there is no interleaving window *within* one `resolve()`/
    `revoke_client()` call; what this proves is that concurrent request
    handling around that boundary is itself well-behaved.)"""
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(SALES_READ_CLIENT_ID)
    state = gateway_module.get_current_state()

    async def read_call() -> object:
        return await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
            token=token,
        )

    async def revoke_after_delay() -> None:
        await asyncio.sleep(0.02)
        state.entitlement_manager.revoke_client(SALES_READ_CLIENT_ID)

    results = await asyncio.gather(
        read_call(), read_call(), revoke_after_delay(), read_call(), read_call()
    )
    call_results = [r for r in results if r is not None]
    # A crash anywhere above would have propagated out of `gather` already --
    # reaching this line at all is the "never crash" half of the property.
    assert all(hasattr(r, "is_error") for r in call_results)

    final = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
        token=token,
    )
    assert final.is_error is True


def test_approval_grant_cannot_be_consumed_twice_under_concurrent_replay() -> None:
    """README.md §46 "approval replay", the concurrency variant:
    `ApprovalService.check_and_consume`'s check-then-set must be atomic
    under real OS thread parallelism (not just against sequential replay,
    already proven in `tests/unit/test_approval.py`), or two attackers
    racing the same single-use grant could both succeed. Exercises the
    `threading.Lock` added in `emcp_bus.approval.service.ApprovalService`
    for exactly this property."""
    from emcp_bus.approval.service import ApprovalService

    service = ApprovalService()
    arguments = {"amount": 50_000}
    request = service.request(
        client_profile="Finance.Payments",
        tool="finance.payment.execute",
        arguments=arguments,
        reason_code="APPROVAL_THRESHOLD_EXCEEDED",
    )
    service.grant(request.approval_id)

    def attempt(_: int) -> bool:
        return service.check_and_consume(
            client_profile="Finance.Payments",
            tool="finance.payment.execute",
            arguments=arguments,
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(20)))

    assert results.count(True) == 1


async def test_bulk_read_access_produces_a_fully_correlated_audit_trail(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §46 "bulk exfiltration using legitimate read tools": this
    RI implements no request-rate limiting or anomaly detection at the
    Gateway -- a real, disclosed gap (RI/README.md "Limitações conhecidas").
    N legitimate reads in a row are all individually ALLOWed; nothing here
    pretends otherwise. What this proves is the compensating control
    README.md §27 asks for: every one of those N calls produces its own
    fully correlated `tool_call_allowed` audit event (a distinct
    `decision_id` each), so a bulk-exfiltration pattern is fully
    reconstructable after the fact from the audit trail even though it is
    not prevented in real time."""
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(SALES_READ_CLIENT_ID)
    sink = InMemoryAuditSink()
    gateway_module.get_current_state().audit_sink = sink

    call_count = 20
    for _ in range(call_count):
        result = await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
            token=token,
        )
        assert result.is_error is not True

    allowed_events = [e for e in sink.events if e.event_type == "tool_call_allowed"]
    assert len(allowed_events) == call_count
    assert len({e.decision_id for e in allowed_events}) == call_count
