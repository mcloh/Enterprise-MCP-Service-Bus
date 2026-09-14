"""Generic REST adapter (EP-06-T04, README.md §6.7).

Real httpx request/response handling against an `httpx.MockTransport`
in-process endpoint -- no real REST backend exists in this RI (both example
domains are MCP-native, see the module docstring in rest_adapter.py), so this
is the closest equivalent to "real dependency, fake network" available for
this specific adapter.
"""

from __future__ import annotations

import json

import httpx
import pytest

from emcp_bus.fabric.adapters.rest_adapter import (
    RestAdapter,
    RestBackendConfig,
    RestOperation,
    UnknownOperationError,
)

CONFIG = RestBackendConfig(
    backend="crm-rest",
    base_url="https://crm.example",
    operations={
        "crm.customer.get": RestOperation(method="GET", path="/v2/customers/{customer_id}"),
        "crm.customer.create": RestOperation(method="POST", path="/v2/customers"),
    },
)


def _adapter(handler: httpx.MockTransport) -> RestAdapter:
    client = httpx.AsyncClient(base_url=CONFIG.base_url, transport=handler)
    return RestAdapter(CONFIG, client=client)


async def test_get_operation_substitutes_path_placeholder_and_sends_remaining_as_query() -> None:
    captured: dict[str, httpx.Request] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"customer_id": "cust-001", "name": "Aurora Ltda"})

    adapter = _adapter(httpx.MockTransport(handle))

    result = await adapter.call("crm.customer.get", {"customer_id": "cust-001", "region": "BR-SP"})

    assert result == {"customer_id": "cust-001", "name": "Aurora Ltda"}
    request = captured["request"]
    assert request.url.path == "/v2/customers/cust-001"
    assert dict(request.url.params) == {"region": "BR-SP"}
    await adapter.aclose()


async def test_post_operation_sends_remaining_arguments_as_json_body() -> None:
    captured: dict[str, httpx.Request] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"customer_id": "cust-002"})

    adapter = _adapter(httpx.MockTransport(handle))

    result = await adapter.call("crm.customer.create", {"name": "Boreal S.A."})

    assert result == {"customer_id": "cust-002"}
    body = json.loads(captured["request"].content)
    assert body == {"name": "Boreal S.A."}
    await adapter.aclose()


async def test_bearer_token_is_forwarded_as_authorization_header() -> None:
    captured: dict[str, httpx.Request] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={})

    adapter = _adapter(httpx.MockTransport(handle))

    await adapter.call(
        "crm.customer.get", {"customer_id": "cust-001"}, bearer_token="outbound-token"
    )

    assert captured["request"].headers["authorization"] == "Bearer outbound-token"
    await adapter.aclose()


async def test_unconfigured_capability_raises() -> None:
    adapter = _adapter(httpx.MockTransport(lambda request: httpx.Response(200, json={})))

    with pytest.raises(UnknownOperationError):
        await adapter.call("crm.customer.delete", {})
    await adapter.aclose()


async def test_backend_error_status_raises() -> None:
    adapter = _adapter(httpx.MockTransport(lambda request: httpx.Response(500)))

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.call("crm.customer.get", {"customer_id": "cust-001"})
    await adapter.aclose()
