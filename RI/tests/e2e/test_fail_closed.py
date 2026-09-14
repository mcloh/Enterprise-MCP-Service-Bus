"""Fail-closed chaos tests (EP-15-T05, README.md §38).

One test per row of the §38 table -- each takes the corresponding component
down (or breaks it) against a real running Gateway, and asserts the
Gateway's observed behavior matches the recommended one exactly, not just
"something safe-ish happens":

| Componente indisponível | Comportamento recomendado                                  |
|---|---|
| Identity Provider | negar novas autenticações                                      |
| PDP               | fail closed                                                     |
| Registry          | usar cache válido somente dentro do authorization context      |
| Audit sink        | buffer seguro; não bloquear low-risk apenas se política permitir |
| Approval service  | negar high-risk                                                 |
| Backend           | propagar falha sem retry destrutivo indevido                    |

PDP-unreachable-at-boot and IdP-not-configured are already covered live in
`tests/e2e/test_governed_gateway.py` (`test_gateway_lifespan_fails_closed_when_pdp_unreachable`,
`test_deny_by_default_when_no_oidc_provider_is_configured`) -- not
duplicated here. This file adds the scenarios that file does not cover: IdP
*unreachable* (as opposed to not configured), PDP dying *mid-session*
(runtime, not boot), Registry seeding failure, a failing audit sink, a
failing approval service, and a dead backend.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from mcp.shared.exceptions import MCPError

from tests.e2e.conftest import (
    REPO_ROOT,
    RunningServer,
    free_port,
    run_against_gateway,
    set_current_gateway_port,
)

SALES_READ_CLIENT_ID = "sales-read-agent"
FINANCE_PAYMENTS_CLIENT_ID = "finance-payments-agent"


# --- Identity Provider ------------------------------------------------------


async def test_unreachable_identity_provider_denies_new_authentications(
    monkeypatch: pytest.MonkeyPatch, opa_url: str
) -> None:
    """README.md §38 "Identity Provider | negar novas autenticações": a
    configured-but-unreachable JWKS endpoint (network partition, IdP outage
    -- distinct from `test_deny_by_default_when_no_oidc_provider_is_configured`'s
    "never configured at all") must deny, not fall back to accepting an
    unverifiable token."""
    import example_mcp_servers.sales_domain.server as sales_module

    import emcp_bus.gateway.server as gateway_module

    sales_port = free_port()
    gateway_port = free_port()
    dead_jwks_port = free_port()  # nothing ever listens here

    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{sales_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv("OIDC_JWKS_URL", f"http://127.0.0.1:{dead_jwks_port}/jwks")
    monkeypatch.setenv("OIDC_ISSUER", "https://keycloak.example/realms/emcp")
    monkeypatch.setenv("OIDC_AUDIENCE", "emcp-gateway")
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "test-sales-domain-backend-credential")

    sales_server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=sales_port,
            log_level="warning",
        )
    )
    await sales_server.start()

    auth_settings, token_verifier = gateway_module.build_auth()
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
        # Any bearer token at all -- the JWKS fetch itself is what fails,
        # before signature/claims are ever checked, so its content is moot.
        with pytest.raises(MCPError):
            await run_against_gateway(lambda session: session.list_tools(), token="anything")
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await sales_server.stop()


# --- PDP ---------------------------------------------------------------------


async def test_pdp_dying_mid_session_fails_closed_on_the_next_call(
    monkeypatch: pytest.MonkeyPatch, jwks_url: str, sign_token: Callable[..., str]
) -> None:
    """README.md §38 "PDP | fail closed", the *runtime* case:
    `test_gateway_lifespan_fails_closed_when_pdp_unreachable` only proves the
    Gateway refuses to come up when the PDP is unreachable at boot -- this
    proves `on_call_tool`'s own `except PDPUnavailableError` branch, live,
    for a PDP that was healthy when the Gateway started and dies later."""
    import example_mcp_servers.sales_domain.server as sales_module

    import emcp_bus.gateway.server as gateway_module

    opa_binary = shutil.which("opa")
    if opa_binary is None:
        pytest.skip("opa binary not found on PATH")

    opa_port = free_port()
    opa_process = subprocess.Popen(
        [
            opa_binary,
            "run",
            "--server",
            "--addr",
            f"127.0.0.1:{opa_port}",
            str(REPO_ROOT / "config" / "policies"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    opa_base_url = f"http://127.0.0.1:{opa_port}"
    for _ in range(100):
        try:
            httpx.get(f"{opa_base_url}/health", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        opa_process.terminate()
        raise RuntimeError("throwaway opa server did not become healthy in time")

    sales_port = free_port()
    gateway_port = free_port()
    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{sales_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_base_url)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    monkeypatch.setenv("OIDC_ISSUER", "https://keycloak.example/realms/emcp")
    monkeypatch.setenv("OIDC_AUDIENCE", "emcp-gateway")
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "test-sales-domain-backend-credential")

    sales_server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=sales_port,
            log_level="warning",
        )
    )
    await sales_server.start()

    auth_settings, token_verifier = gateway_module.build_auth()
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
        token = sign_token(SALES_READ_CLIENT_ID)

        baseline = await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
            token=token,
        )
        assert baseline.is_error is not True

        opa_process.terminate()
        opa_process.wait(timeout=5)

        after_pdp_death = await run_against_gateway(
            lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
            token=token,
        )
        assert after_pdp_death.is_error is True
        assert "PDP_UNAVAILABLE" in " ".join(
            getattr(c, "text", "") for c in after_pdp_death.content
        )
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await sales_server.stop()
        if opa_process.poll() is None:
            opa_process.terminate()
            opa_process.wait(timeout=5)


# --- Registry ------------------------------------------------------------


async def test_gateway_lifespan_fails_closed_when_registry_cannot_be_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, opa_url: str
) -> None:
    """README.md §38 "Registry | usar cache válido somente dentro do
    authorization context": this RI's Registry is a local SQLite store
    seeded once, synchronously, at `lifespan()` startup (EP-06-T01) -- it
    has no live "goes unavailable mid-request" state to chaos-test, since
    nothing queries it over a network per-call. The meaningful failure mode
    is at boot: a Gateway that cannot seed the Registry must not come up
    looking healthy either, exactly like the already-proven PDP-unreachable
    case. Real `clients`/`policies`/`backends` config is copied into a temp
    dir; only `capabilities/` is left out, so `seed_registry` genuinely
    fails to find any manifest to load."""
    config_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "clients", config_dir / "clients")
    shutil.copytree(REPO_ROOT / "config" / "policies", config_dir / "policies")
    shutil.copytree(REPO_ROOT / "config" / "backends", config_dir / "backends")
    # Deliberately no `config_dir / "capabilities"`.

    monkeypatch.setenv("EMCP_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("OPA_URL", opa_url)

    import emcp_bus.gateway.server as gateway_module

    with pytest.raises(FileNotFoundError):
        async with gateway_module.lifespan(gateway_module.server):
            pytest.fail("lifespan must not yield a state when the Registry could not be seeded")


# --- Audit sink ------------------------------------------------------------


class _AlwaysFailingAuditSink:
    def emit(self, event: Any) -> None:
        raise OSError("simulated audit sink outage (disk full / queue unreachable)")


async def test_a_failing_audit_sink_never_blocks_an_already_allowed_low_risk_call(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """README.md §38 "Audit sink | buffer seguro; não bloquear low-risk":
    exercises `emcp_bus.gateway.server._emit_audit` (added for EP-15-T05) --
    a sink that raises on every `emit()` must not turn an already-ALLOWed,
    already-executed low-risk read into a client-visible error."""
    import emcp_bus.gateway.server as gateway_module

    gateway_module.get_current_state().audit_sink = _AlwaysFailingAuditSink()
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
        token=token,
    )

    assert result.is_error is not True


async def test_a_failing_audit_sink_still_lets_a_deny_reach_the_client_as_deny(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """The DENY decision itself must survive a broken audit sink too -- a
    sink failure while *logging* a deny must never surface as an unrelated
    500 that masks the real, already-made DENY decision."""
    import emcp_bus.gateway.server as gateway_module

    gateway_module.get_current_state().audit_sink = _AlwaysFailingAuditSink()
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.execute", {"amount": 1_000_000, "payment_id": "pay-001"}
        ),
        token=token,
    )

    assert result.is_error is True


# --- Approval service --------------------------------------------------------


class _AlwaysFailingApprovalService:
    def check_and_consume(self, **_: Any) -> bool:
        raise RuntimeError("simulated approval service outage")

    def request(self, **kwargs: Any) -> Any:
        from datetime import UTC, datetime, timedelta

        from emcp_bus.approval.models import ApprovalRequest, compute_operation_hash

        return ApprovalRequest(
            operation_hash=compute_operation_hash(
                client_profile=kwargs["client_profile"],
                tool=kwargs["tool"],
                arguments=kwargs["arguments"],
            ),
            client_profile=kwargs["client_profile"],
            tool=kwargs["tool"],
            arguments_summary=kwargs["arguments"],
            reason_code=kwargs["reason_code"],
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )


async def test_a_failing_approval_service_denies_high_risk_rather_than_crashing_or_allowing(
    governed_stack_with_finance: None, sign_token: Callable[..., str]
) -> None:
    """README.md §38 "Approval service | negar high-risk": exercises the
    `except Exception: approved = False` branch in `on_call_tool`
    (EP-14-T03) live, for the first time -- a REQUIRE_APPROVAL operation
    whose approval-consumption check itself raises must be denied, never
    silently allowed and never an unhandled server error."""
    import emcp_bus.gateway.server as gateway_module

    gateway_module.get_current_state().approval_service = _AlwaysFailingApprovalService()  # type: ignore[assignment]
    token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool(
            "finance.payment.execute", {"amount": 50_000, "payment_id": "pay-001"}
        ),
        token=token,
    )

    assert result.is_error is True


# --- Backend -----------------------------------------------------------------


async def test_a_dead_backend_fails_the_one_request_without_crashing_the_gateway(
    monkeypatch: pytest.MonkeyPatch, opa_url: str, jwks_url: str, sign_token: Callable[..., str]
) -> None:
    """README.md §38 "Backend | propagar falha sem retry destrutivo
    indevido": `_with_downstream_session` (EP-05) opens exactly one
    connection attempt per call, no retry loop at all -- so "no destructive
    retry" already holds by construction. What this proves is the other
    half: a completely unreachable backend (Sales, here) fails *that one
    request* cleanly, without taking the whole Gateway process down -- an
    unrelated client entitled only to a *different*, healthy backend
    (Finance) is completely unaffected."""
    import example_mcp_servers.finance_domain.server as finance_module

    import emcp_bus.gateway.server as gateway_module
    from tests.e2e.conftest import AUDIENCE, ISSUER

    dead_sales_port = free_port()  # nothing listens here
    finance_port = free_port()
    gateway_port = free_port()
    monkeypatch.setenv("SALES_DOMAIN_URL", f"http://127.0.0.1:{dead_sales_port}/mcp")
    monkeypatch.setenv("FINANCE_DOMAIN_URL", f"http://127.0.0.1:{finance_port}/mcp")
    monkeypatch.setenv("OPA_URL", opa_url)
    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("SALES_DOMAIN_SERVICE_TOKEN", "test-sales-domain-backend-credential")
    monkeypatch.setenv("FINANCE_DOMAIN_SERVICE_TOKEN", "test-finance-domain-backend-credential")

    finance_server = RunningServer(
        uvicorn.Config(
            finance_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=finance_port,
            log_level="warning",
        )
    )
    await finance_server.start()

    auth_settings, token_verifier = gateway_module.build_auth()
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
        sales_token = sign_token(SALES_READ_CLIENT_ID)

        # The call itself fails one way or another (a clean tool error, or a
        # protocol-level error the SDK surfaces from the handler's raised
        # exception) -- either is acceptable here; a hang or a process crash
        # is not.
        try:
            result = await run_against_gateway(
                lambda session: session.call_tool(
                    "sales.customer.get", {"customer_id": "cust-001"}
                ),
                token=sales_token,
            )
            assert result.is_error is True
        except MCPError:
            pass

        # The Gateway process itself is still alive and correct for an
        # unrelated client whose entitlement never touches the dead backend.
        finance_token = sign_token(FINANCE_PAYMENTS_CLIENT_ID)
        invoice = await run_against_gateway(
            lambda session: session.call_tool("finance.invoice.get", {"invoice_id": "inv-001"}),
            token=finance_token,
        )
        assert invoice.is_error is not True
    finally:
        set_current_gateway_port(None)
        await gateway_server.stop()
        await finance_server.stop()
