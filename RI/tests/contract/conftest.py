"""Contract tests connect directly to a domain server -- never through the
Gateway -- because a tool's input/output contract is a property of the
domain server itself (ADR-023: it's "dumb" about authorization, but not
about its own data shape), independent of who is or isn't entitled to call
it. Reuses `RunningServer`/`free_port` from the e2e suite rather than
duplicating them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import mcp_types as types
import pytest
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import (  # type: ignore[attr-defined]
    create_mcp_http_client,
    streamable_http_client,
)

from tests.e2e.conftest import RunningServer, free_port


async def call_tool_directly(
    server_url: str, tool_name: str, arguments: dict[str, Any]
) -> types.CallToolResult:
    """No auth header at all -- these servers are `main()`-unwrapped here
    (no `BackendCredentialGate`), matching how the rest of the e2e suite
    already constructs them for in-process tests."""
    async with (
        create_mcp_http_client() as http_client,
        streamable_http_client(server_url, http_client=http_client) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
        if not isinstance(result, types.CallToolResult):
            raise TypeError(f"Unexpected result type: {type(result)!r}")
        return result


@pytest.fixture
async def sales_domain_url() -> AsyncIterator[str]:
    import example_mcp_servers.sales_domain.server as sales_module

    port = free_port()
    server = RunningServer(
        uvicorn.Config(
            sales_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    await server.start()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        await server.stop()


@pytest.fixture
async def finance_domain_url() -> AsyncIterator[str]:
    import example_mcp_servers.finance_domain.server as finance_module

    port = free_port()
    server = RunningServer(
        uvicorn.Config(
            finance_module.server.streamable_http_app(host="127.0.0.1"),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    await server.start()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        await server.stop()
