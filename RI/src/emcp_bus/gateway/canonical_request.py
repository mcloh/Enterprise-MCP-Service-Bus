"""Header/body consistency check (EP-05-T08, README.md §22, SEP-2243).

The 2026-07-28 MCP revision has clients mirror the JSON-RPC `method` (and,
for `tools/call`/`prompts/get`/`resources/read`, the named resource) into
the `Mcp-Method`/`Mcp-Name` HTTP headers -- `mcp`'s own `ClientSession`
already sends both on every request (verified against the installed SDK).
The SDK's *modern per-request-envelope* transport path validates this
consistency internally, but only for that one wire mode (a fresh
`_meta.protocolVersion` on every request, no `initialize` handshake) --
this RI's Gateway (like most current clients, including its own test
suite) uses the classic session handshake instead, where nothing upstream
of application code checks it. This module is that check: if both a header
and the corresponding body field are present, they must agree, or the
request is rejected before it ever reaches authentication/authorization --
producing one canonical (method, name) pair a downstream handler can trust,
rather than silently picking one of two disagreeing sources (README.md
§22, "produzir representação canônica única").

Headers absent entirely (a client that doesn't implement SEP-2243) are not
an error -- this is a consistency check, not a mandate that every client
adopt the new headers.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, NAME_BEARING_METHODS
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def find_header_body_mismatch(
    body: bytes, *, method_header: str | None, name_header: str | None
) -> str | None:
    """Reason string if `body` disagrees with the given header values, else `None`.

    A body that isn't valid JSON, or isn't a JSON-RPC request shape, is left
    for the app's own JSON-RPC parsing to reject -- this function only rules
    on cases where it can positively compare a body value against a header.
    """
    if method_header is None and name_header is None:
        return None
    try:
        parsed: Any = json.loads(body) if body else None
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    body_method = parsed.get("method")
    if method_header is not None and isinstance(body_method, str) and method_header != body_method:
        return (
            f"{MCP_METHOD_HEADER} header ({method_header!r}) does not match "
            f"body.method ({body_method!r})"
        )

    if name_header is not None and isinstance(body_method, str):
        name_key = NAME_BEARING_METHODS.get(body_method)
        if name_key is not None:
            params = parsed.get("params")
            body_name = params.get(name_key) if isinstance(params, dict) else None
            if isinstance(body_name, str) and name_header != body_name:
                return (
                    f"{MCP_NAME_HEADER} header ({name_header!r}) does not match "
                    f"body.params.{name_key} ({body_name!r})"
                )
    return None


class CanonicalRequestGate:
    """ASGI middleware wrapping the Gateway's MCP app: rejects a POST whose
    `Mcp-Method`/`Mcp-Name` headers disagree with its JSON-RPC body, before
    the request ever reaches authentication or `on_list_tools`/`on_call_tool`."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self._app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        method_header = headers.get(MCP_METHOD_HEADER)
        name_header = headers.get(MCP_NAME_HEADER)
        if method_header is None and name_header is None:
            await self._app(scope, receive, send)
            return

        buffered: list[Message] = []
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            buffered.append(message)
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        mismatch = find_header_body_mismatch(
            body, method_header=method_header, name_header=name_header
        )
        if mismatch is not None:
            response = JSONResponse(
                {"error": "header_body_mismatch", "detail": mismatch}, status_code=400
            )
            await response(scope, receive, send)
            return

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return {"type": "http.disconnect"}

        await self._app(scope, replay_receive, send)
