"""EP-05-T02/T04 governed Gateway: the actual security invariants of
README.md §45 ("Critérios de aceite de segurança"), run against the real
chain -- real OIDC token validation (JWKS server standing in for Keycloak),
real OPA-backed PDP, real EntitlementManager loading the real config/
YAML files.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from mcp.shared.exceptions import MCPError

from tests.e2e.conftest import run_against_gateway

SALES_READ_CLIENT_ID = "sales-read-agent"
SALES_WRITE_CLIENT_ID = "sales-write-agent"
FINANCE_PAYMENTS_CLIENT_ID = "finance-payments-agent"


async def test_teste1_unauthorized_discovery(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 1: finance.createPayment MUST NOT be returned to Sales.Read."""
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(lambda session: session.list_tools(), token=token)

    tool_names = {tool.name for tool in result.tools}
    assert "finance.payment.execute" not in tool_names
    assert "sales.quote.create" not in tool_names  # Sales.Write-only, not Sales.Read


async def test_teste2_direct_unauthorized_call(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 2: calling a known-but-unentitled tool directly, without
    ever having seen it in tools/list, must still DENY."""
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", {"amount": 1_000_000}),
        token=token,
    )

    assert result.is_error is True
    assert "Access denied" in _text(result)


async def test_teste4_agent_role_spoofing_has_no_effect(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 4: nothing the caller declares in tool arguments
    (an agent-shaped 'role' claim in this case) can expand entitlement."""
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.execute",
            {"amount": 100, "role": "finance-admin", "client_profile": "Finance.Payments"},
        ),
        token=token,
    )

    assert result.is_error is True


async def test_unauthenticated_request_sees_no_tools_and_is_denied(
    governed_stack: None,
) -> None:
    """README.md §5: 'No entitlement -> no discovery -> no execution'.

    With OIDC configured, the SDK's own `RequireAuthMiddleware` rejects a
    connection with no bearer token before the MCP session handshake
    (`initialize`) ever completes -- stricter than this Gateway's own
    handler-level `access_token is None` checks (`on_list_tools`/
    `on_call_tool`), which exist as the deny-by-default backstop for the
    *other* supported deployment mode: no OIDC configured at all (see
    `GatewayConfig`/`build_auth` in emcp_bus/gateway/server.py), where every
    request reaches the handlers unauthenticated and those checks are what
    enforces "no discovery, no execution" instead.
    """
    with pytest.raises(MCPError):
        await run_against_gateway(lambda session: session.list_tools())


async def test_expired_token_is_denied(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 3 (adjacent)/§46: expired token, adversarial scenario."""
    token = sign_token(SALES_READ_CLIENT_ID, expires_in_seconds=-3600)

    with pytest.raises(MCPError):
        await run_against_gateway(lambda session: session.list_tools(), token=token)


async def test_wrong_audience_token_is_denied(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §45 Teste 8: a token issued for a different resource server."""
    token = sign_token(SALES_READ_CLIENT_ID, audience="some-other-service")

    with pytest.raises(MCPError):
        await run_against_gateway(lambda session: session.list_tools(), token=token)


async def test_forged_signature_token_is_denied(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §46: stolen/forged token, signed by a key not in the JWKS."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign_token(SALES_READ_CLIENT_ID, signing_key=forged_key)

    with pytest.raises(MCPError):
        await run_against_gateway(lambda session: session.list_tools(), token=token)


async def test_transaction_policy_denies_over_limit_even_though_entitled(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §25 Passo 2: sales.quote.create IS in Sales.Write's entitlement,
    but the transaction policy still denies an amount above the profile's limit."""
    token = sign_token(SALES_WRITE_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "sales.quote.create", {"amount": 999_999_999, "region": "BR-SP"}
        ),
        token=token,
    )

    assert result.is_error is True
    assert "TRANSACTION_POLICY_DENIED" in _text(result)


async def test_require_approval_is_denied_without_a_grant(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §26: Finance.Payments allows payment.execute above the approval
    threshold (README.md §7.2/§17 profile) but must never silently upgrade a
    REQUIRE_APPROVAL to ALLOW -- the first attempt of any such call is always
    denied, since no approval has been granted for it yet (EP-14-T02)."""
    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", {"amount": 50_000}),
        token=token,
    )

    assert result.is_error is True
    assert "REQUIRE_APPROVAL" in _text(result)


async def test_full_approval_cycle_grant_then_execute_then_replay_denied(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """EP-14 end to end: deny (no grant) -> out-of-band grant -> the *same*
    call now reaches the real backend -> a second attempt of the identical
    call is denied again (README.md §46, single-use "approval replay").

    Uses Sales.Write + sales.quote.create (approval_threshold=100000,
    config/clients/profiles/sales-write.yaml); see
    `test_finance_full_approval_cycle_routes_through_fabric_to_finance_domain`
    below for the same cycle proven against the Finance domain (EP-06-T03).
    """
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(SALES_WRITE_CLIENT_ID)
    arguments = {"customer_id": "cust-001", "amount": 150_000, "region": "BR-SP"}

    first_attempt = await run_against_gateway(
        lambda session: session.call_tool("sales.quote.create", arguments), token=token
    )
    assert first_attempt.is_error is True
    assert "REQUIRE_APPROVAL" in _text(first_attempt)
    approval_id = _text(first_attempt).rsplit(":", 1)[-1]

    # Out-of-band: an approver grants the specific request the Gateway itself
    # created (see `on_call_tool`'s REQUIRE_APPROVAL branch) -- not a new one
    # constructed by the test, proving the Gateway and the approver are
    # looking at the same `ApprovalService` instance (`get_current_state()`).
    gateway_module.get_current_state().approval_service.grant(approval_id)

    granted_attempt = await run_against_gateway(
        lambda session: session.call_tool("sales.quote.create", arguments), token=token
    )
    assert granted_attempt.is_error is not True
    assert granted_attempt.structured_content is not None
    assert granted_attempt.structured_content["status"] == "draft"

    replay_attempt = await run_against_gateway(
        lambda session: session.call_tool("sales.quote.create", arguments), token=token
    )
    assert replay_attempt.is_error is True
    assert "REQUIRE_APPROVAL" in _text(replay_attempt)


async def test_sales_client_tools_list_never_includes_finance_tools(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """EP-06-T01: the Fabric router queries only the backends a client's
    entitlement actually touches -- a Sales.Read client's tools/list never
    even connects to the Finance backend."""
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(lambda session: session.list_tools(), token=token)

    tool_names = {tool.name for tool in result.tools}
    assert tool_names == {
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
    }


async def test_finance_client_tools_list_never_includes_sales_tools(
    governed_stack_with_finance: None, sign_token: Callable[..., str]
) -> None:
    """EP-06-T01, the mirror image: a Finance.Payments client's tools/list
    routes to the Finance backend only, never Sales."""
    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    result = await run_against_gateway(lambda session: session.list_tools(), token=token)

    tool_names = {tool.name for tool in result.tools}
    assert tool_names == {
        "finance.invoice.get",
        "finance.payment.create",
        "finance.payment.execute",
    }


# EP-05-T03's SEP-2549 `ttl_ms`/`cache_scope` fields are per-version wire
# vocabulary (`mcp_types._v2026_07_28`) that the SDK's own serialization
# sieve strips for every earlier protocol revision (verified: neither field
# exists in any pre-2026-07-28 per-version result model at all). This RI's
# entire transport uses the classic session `initialize()` handshake, which
# never negotiates 2026-07-28 (that revision is reached only via the
# stateless per-request `server/discover` mode this RI does not use) -- so
# there is no e2e test here asserting on `result.cache_scope`/`result.ttl_ms`:
# whatever the Gateway sets internally, a client on this transport only ever
# sees the field's own class default, making such an assertion pass
# regardless of what the Gateway actually computed. `tools_list_cache_hint()`
# itself (always `scope="private"`, configurable `ttl_ms`) is the real,
# meaningful test -- see tests/unit/test_gateway_cache.py -- and
# `emcp_bus.gateway.cache`'s module docstring has the full, verified
# explanation.


async def test_finance_full_approval_cycle_routes_through_fabric_to_finance_domain(
    governed_stack_with_finance: None, sign_token: Callable[..., str]
) -> None:
    """EP-06-T01/T03 + EP-14 end to end against the *Finance* domain server:
    the Fabric router resolves finance.payment.create/execute to the Finance
    backend, and the same deny -> grant -> execute -> replay-denied cycle as
    `test_full_approval_cycle_grant_then_execute_then_replay_denied` (Sales)
    holds identically here."""
    import emcp_bus.gateway.server as gateway_module

    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    create_result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.create", {"invoice_id": "inv-002", "amount": 5_000}
        ),
        token=token,
    )
    assert create_result.is_error is not True
    assert create_result.structured_content is not None
    payment_id = create_result.structured_content["payment_id"]

    execute_arguments = {"payment_id": payment_id, "amount": 50_000}
    first_attempt = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", execute_arguments),
        token=token,
    )
    assert first_attempt.is_error is True
    assert "REQUIRE_APPROVAL" in _text(first_attempt)
    approval_id = _text(first_attempt).rsplit(":", 1)[-1]

    gateway_module.get_current_state().approval_service.grant(approval_id)

    granted_attempt = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", execute_arguments),
        token=token,
    )
    assert granted_attempt.is_error is not True
    assert granted_attempt.structured_content is not None
    assert granted_attempt.structured_content["status"] == "executed"

    replay_attempt = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", execute_arguments),
        token=token,
    )
    assert replay_attempt.is_error is True
    assert "REQUIRE_APPROVAL" in _text(replay_attempt)


async def test_gateway_lifespan_fails_closed_when_pdp_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """README.md §38: PDP indisponível -> fail closed, never ALLOW-by-omission.

    A Gateway that cannot sync entitlements to its PDP at startup must not
    come up looking healthy (EP-05-T06): its `lifespan` must raise, not swallow
    the error and yield a state built on an empty/stale entitlement sync.
    """
    from tests.e2e.conftest import free_port

    monkeypatch.setenv("OPA_URL", f"http://127.0.0.1:{free_port()}")  # nothing listening here

    import emcp_bus.gateway.server as gateway_module
    from emcp_bus.pdp.client import PDPUnavailableError

    with pytest.raises(PDPUnavailableError):
        async with gateway_module.lifespan(gateway_module.server):
            pytest.fail("lifespan must not yield a state when the PDP sync failed")


async def test_deny_by_default_when_no_oidc_provider_is_configured(
    monkeypatch: pytest.MonkeyPatch, opa_url: str
) -> None:
    """README.md §5: the *other* supported deployment mode (no OIDC provider
    configured at all -- `OIDC_JWKS_URL`/`OIDC_ISSUER` unset). No
    `RequireAuthMiddleware` is installed in this mode (see `build_auth`), so
    every request reaches the handlers with `get_access_token() is None`,
    and it is the Gateway's own handler-level checks that must deny by
    default -- this is the code path Teste 1-style discovery filtering and
    Teste 2-style execution denial fall back to without an IdP.
    """
    import uvicorn

    from tests.e2e.conftest import (
        RunningServer,
        free_port,
        run_against_gateway,
        set_current_gateway_port,
    )

    sales_port = free_port()
    gateway_port = free_port()

    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{sales_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "test-sales-domain-backend-credential")
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)

    import example_mcp_servers.sales_domain.server as sales_module

    sales_server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=sales_port,
            log_level="warning",
        )
    )
    await sales_server.start()

    import emcp_bus.gateway.server as gateway_module

    auth_settings, token_verifier = gateway_module.build_auth()
    assert (auth_settings, token_verifier) == (None, None)  # confirms the mode under test

    gateway_server = RunningServer(
        uvicorn.Config(
            gateway_module.build_app(auth_settings, token_verifier, host="127.0.0.1"),
            host="127.0.0.1",
            port=gateway_port,
            log_level="warning",
        )
    )
    await gateway_server.start()
    set_current_gateway_port(gateway_port)
    try:
        list_result = await run_against_gateway(lambda session: session.list_tools())
        assert list_result.tools == []

        call_result = await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"})
        )
        assert call_result.is_error is True
        assert "UNAUTHENTICATED" in _text(call_result)
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await sales_server.stop()


def _text(result: object) -> str:
    content = getattr(result, "content", [])
    return " ".join(getattr(item, "text", "") for item in content)
