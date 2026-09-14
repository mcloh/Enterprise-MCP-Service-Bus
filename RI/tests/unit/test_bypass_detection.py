"""Anti-bypass credential gate for domain servers (EP-05-T07, README.md §21).

Real ASGI request handling (`httpx.ASGITransport`) against a real
`BackendCredentialGate`-wrapped app -- not a hand-mocked request object.
"""

from __future__ import annotations

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from emcp_bus.audit.bypass_detection import BackendCredentialGate
from emcp_bus.audit.sink import InMemoryAuditSink


async def _ok(request: object) -> JSONResponse:
    return JSONResponse({"ok": True})


def _gated_app(audit_sink: InMemoryAuditSink | None = None) -> BackendCredentialGate:
    inner = Starlette(routes=[Route("/mcp", _ok, methods=["POST"])])
    return BackendCredentialGate(
        inner,
        expected_token="the-real-gateway-credential",
        backend="sales-domain",
        audit_sink=audit_sink,
    )


async def test_request_with_correct_bearer_token_reaches_the_app() -> None:
    app = _gated_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/mcp", headers={"Authorization": "Bearer the-real-gateway-credential"}
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_request_with_no_authorization_header_is_rejected() -> None:
    sink = InMemoryAuditSink()
    app = _gated_app(sink)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/mcp")

    assert response.status_code == 401
    assert len(sink.events) == 1
    assert sink.events[0].event_type == "bypass_attempt_detected"
    assert sink.events[0].payload["reason"] == "missing_credential"


async def test_request_with_wrong_bearer_token_is_rejected() -> None:
    """This is the concrete Teste 7 (§45, 'Gateway bypass') scenario: someone
    who can reach the domain server's port directly, but does not hold the
    Gateway's outbound service credential, must not reach a tool handler."""
    sink = InMemoryAuditSink()
    app = _gated_app(sink)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/mcp", headers={"Authorization": "Bearer someone-elses-token"}
        )

    assert response.status_code == 401
    assert sink.events[0].payload["reason"] == "wrong_credential"


async def test_a_stolen_inbound_client_token_does_not_satisfy_the_gate() -> None:
    """README.md §20/ADR-006: even a real, valid *inbound* MCP Client token
    is not the outbound credential -- presenting one here must still fail."""
    app = _gated_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/mcp", headers={"Authorization": "Bearer some-inbound-oidc-access-token"}
        )

    assert response.status_code == 401
