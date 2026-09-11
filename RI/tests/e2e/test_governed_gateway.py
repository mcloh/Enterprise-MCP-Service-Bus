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


async def test_require_approval_is_denied_pending_ep14(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §26: Finance.Payments allows payment.execute below the approval
    threshold (README.md §7.2/§17 profile) but must never silently upgrade a
    REQUIRE_APPROVAL to ALLOW -- and EP-14 (approval workflow) does not exist
    yet in this milestone, so the only safe outcome is DENY."""
    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool("finance.payment.execute", {"amount": 50_000}),
        token=token,
    )

    assert result.is_error is True
    assert "REQUIRE_APPROVAL" in _text(result)


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

    from tests.e2e.conftest import GATEWAY_PORT, SALES_PORT, RunningServer, run_against_gateway

    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{SALES_PORT}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)

    import example_mcp_servers.sales_domain.server as sales_module

    sales_server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=SALES_PORT,
            log_level="warning",
        )
    )
    await sales_server.start()

    import emcp_bus.gateway.server as gateway_module

    auth_settings, token_verifier = gateway_module.build_auth()
    assert (auth_settings, token_verifier) == (None, None)  # confirms the mode under test

    gateway_server = RunningServer(
        uvicorn.Config(
            gateway_module.server.streamable_http_app(
                host="127.0.0.1", auth=auth_settings, token_verifier=token_verifier
            ),
            host="127.0.0.1",
            port=GATEWAY_PORT,
            log_level="warning",
        )
    )
    await gateway_server.start()
    try:
        list_result = await run_against_gateway(lambda session: session.list_tools())
        assert list_result.tools == []

        call_result = await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"})
        )
        assert call_result.is_error is True
        assert "UNAUTHENTICATED" in _text(call_result)
    finally:
        await gateway_server.stop()
        await sales_server.stop()


def _text(result: object) -> str:
    content = getattr(result, "content", [])
    return " ".join(getattr(item, "text", "") for item in content)
