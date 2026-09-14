"""Example Sales-domain MCP server (EP-06-T02).

Read-only tools (risk tier R1, see README.md §17): customer.search,
customer.get, order.get, inventory.check. Write tools (R2): quote.create,
quote.update. Backed by static mock data -- this server is deliberately
"dumb": it never authorizes anything (see `docs/adr/ADR-023-autorizacao-nunca-vem-do-payload.md`).
Authorization happens exclusively upstream, in the Gateway/PEP (EP-05)
before a call ever reaches this process.

Run directly for local development:

    python -m example_mcp_servers.sales_domain.server
"""

from __future__ import annotations

import itertools
import os

from mcp.server.mcpserver import MCPServer
from starlette.types import ASGIApp

from emcp_bus.audit.bypass_detection import BackendCredentialGate
from emcp_bus.audit.sink import JSONLFileAuditSink
from emcp_bus.common.otel import setup_tracing

setup_tracing("sales-domain-mcp-server")

server = MCPServer(name="sales-domain", version="0.1.0")

_CUSTOMERS: dict[str, dict[str, object]] = {
    "cust-001": {"customer_id": "cust-001", "name": "Aurora Ltda", "region": "BR-SP"},
    "cust-002": {"customer_id": "cust-002", "name": "Boreal S.A.", "region": "BR-RJ"},
}

_ORDERS: dict[str, dict[str, object]] = {
    "ord-001": {"order_id": "ord-001", "customer_id": "cust-001", "status": "shipped"},
}

_INVENTORY: dict[str, int] = {
    "sku-100": 42,
    "sku-200": 0,
}

_QUOTES: dict[str, dict[str, object]] = {}
_quote_ids = itertools.count(1)


@server.tool(name="sales.customer.search", description="Search sales customers by name fragment.")
def customer_search(query: str) -> dict[str, object]:
    matches = [c for c in _CUSTOMERS.values() if query.lower() in str(c["name"]).lower()]
    return {"results": matches}


@server.tool(name="sales.customer.get", description="Get a single sales customer by id.")
def customer_get(customer_id: str) -> dict[str, object]:
    customer = _CUSTOMERS.get(customer_id)
    if customer is None:
        return {"error": "not_found", "customer_id": customer_id}
    return customer


@server.tool(name="sales.order.get", description="Get a single sales order by id.")
def order_get(order_id: str) -> dict[str, object]:
    order = _ORDERS.get(order_id)
    if order is None:
        return {"error": "not_found", "order_id": order_id}
    return order


@server.tool(name="sales.inventory.check", description="Check available inventory for a SKU.")
def inventory_check(sku: str) -> dict[str, object]:
    return {"sku": sku, "available": _INVENTORY.get(sku, 0)}


@server.tool(name="sales.quote.create", description="Create a sales quote for a customer.")
def quote_create(customer_id: str, amount: float, region: str = "BR-SP") -> dict[str, object]:
    quote_id = f"quote-{next(_quote_ids):03d}"
    quote = {
        "quote_id": quote_id,
        "customer_id": customer_id,
        "amount": amount,
        "region": region,
        "status": "draft",
    }
    _QUOTES[quote_id] = quote
    return quote


@server.tool(name="sales.quote.update", description="Update an existing sales quote.")
def quote_update(quote_id: str, amount: float | None = None) -> dict[str, object]:
    quote = _QUOTES.get(quote_id)
    if quote is None:
        return {"error": "not_found", "quote_id": quote_id}
    if amount is not None:
        quote["amount"] = amount
    return quote


def main() -> None:
    host = os.environ.get("SALES_DOMAIN_HOST", "127.0.0.1")
    port = int(os.environ.get("SALES_DOMAIN_PORT", "8100"))
    expected_token = os.environ.get("SALES_DOMAIN_SERVICE_TOKEN")
    audit_log_path = os.environ.get("EMCP_AUDIT_LOG_PATH", "/tmp/emcp-audit.jsonl")

    app: ASGIApp = server.streamable_http_app(host=host)
    if expected_token:
        # EP-05-T07: reject anything that didn't come through the Gateway's
        # outbound identity (EP-07-T01) with the matching service credential.
        app = BackendCredentialGate(
            app,
            expected_token=expected_token,
            backend="sales-domain",
            audit_sink=JSONLFileAuditSink(audit_log_path),
        )

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
