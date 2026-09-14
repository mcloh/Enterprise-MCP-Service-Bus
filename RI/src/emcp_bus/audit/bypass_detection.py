"""Anti-bypass check for domain ("dumb") MCP servers (EP-05-T07, README.md §21, ADR-007).

Network segmentation (docker-compose.yml: domain servers publish no host
port, reachable only on the compose-internal network the Gateway also sits
on) is the primary control. This module is the second, in-process layer:
every domain server call must carry the *outbound* credential only the
Gateway holds (`BackendCredentialProvider`, EP-07-T01) as a bearer token: a
request missing it, or carrying the wrong value, did not come from the
Gateway and is rejected here, before it ever reaches a tool handler.

This is deliberately NOT an authorization decision (ADR-023: domain servers
never decide entitlement/risk) -- it is a bypass/integrity check, equivalent
in spirit to requiring mTLS from a fixed set of peers. The only decision
made here is "did this request present the one credential the Gateway is
configured to send", never "is this client allowed to call this tool".
"""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from emcp_bus.audit.events import bypass_attempt_detected
from emcp_bus.audit.sink import AuditSink


class BackendCredentialGate:
    """ASGI middleware: reject any request not bearing `expected_token`.

    Wrap a domain server's app with this, e.g.:

        app = BackendCredentialGate(server.streamable_http_app(...),
                                     expected_token=..., backend="sales-domain",
                                     audit_sink=...)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        expected_token: str,
        backend: str,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._app = app
        self._expected_token = expected_token
        self._backend = backend
        self._audit_sink = audit_sink

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        presented = _extract_bearer_token(request.headers.get("authorization"))
        if presented is None or not hmac.compare_digest(presented, self._expected_token):
            if self._audit_sink is not None:
                reason = "missing_credential" if presented is None else "wrong_credential"
                self._audit_sink.emit(bypass_attempt_detected(backend=self._backend, reason=reason))
            response = JSONResponse(
                {"error": "backend_credential_required"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if authorization_header is None:
        return None
    scheme, _, value = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value
