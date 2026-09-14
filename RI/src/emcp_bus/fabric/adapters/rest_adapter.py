"""Generic REST adapter (EP-06-T04, README.md §6.7).

Translates one `tools/call` invocation into an HTTP request against a REST
backend described entirely by config (`RestBackendConfig`) -- no new Python
code is needed to expose a new REST backend, only a YAML declaring, per
capability, the HTTP method and a path template (README.md §6.8's
`operation: "GET /v2/customers/{id}"` example). Path placeholders are
substituted from the call's arguments by name; whatever arguments remain
become the JSON body (write methods) or query string (GET/DELETE).

This RI's two example domains (sales, finance; EP-06-T02/T03) are both
MCP-native, so no seed `CapabilityManifest` declares `backend.type: "rest"`
yet, and the Fabric router (EP-06-T01) does not dispatch to this adapter on
any live path today -- it is implemented and unit-tested standalone (real
httpx request/response handling, against an `httpx.MockTransport` in-process
endpoint rather than a real network service, since no real REST example
backend is in scope). Wiring a third, REST-based example backend through
`CapabilityRouter`/the Gateway is possible without any contract change here
(dispatch on `BackendRoute.backend_type == "rest"`), left as unscoped,
non-blocking future work.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel


class RestOperation(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    """Path template, e.g. "/v2/customers/{customer_id}"."""


class RestBackendConfig(BaseModel):
    backend: str
    base_url: str
    operations: dict[str, RestOperation]
    """Capability name -> operation, e.g. {"sales.customer.get": RestOperation(...)}."""


class UnknownOperationError(Exception):
    pass


class RestAdapter:
    """One instance per REST backend; `call` runs one capability invocation."""

    def __init__(
        self, config: RestBackendConfig, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(base_url=config.base_url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call(
        self, capability: str, arguments: dict[str, Any], *, bearer_token: str | None = None
    ) -> dict[str, Any]:
        operation = self._config.operations.get(capability)
        if operation is None:
            raise UnknownOperationError(
                f"REST backend {self._config.backend!r} has no operation configured "
                f"for capability {capability!r}"
            )

        remaining = dict(arguments)
        path = operation.path
        for key in list(remaining):
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(remaining.pop(key)))

        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        if operation.method in ("GET", "DELETE"):
            response = await self._client.request(
                operation.method, path, params=remaining or None, headers=headers
            )
        else:
            response = await self._client.request(
                operation.method, path, json=remaining, headers=headers
            )
        response.raise_for_status()
        if not response.content:
            return {}
        result: dict[str, Any] = response.json()
        return result
