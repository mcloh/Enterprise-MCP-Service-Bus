"""Example Sales-domain MCP server (EP-06-T02, walking-skeleton subset).

Read-only tools (risk tier R1, see README.md §17): customer.search,
customer.get, order.get, inventory.check. Backed by static mock data -- this
server is deliberately "dumb": it never authorizes anything (ADR-023 in
docs/RI-PLANNING.md). Authorization happens exclusively upstream, in the
Gateway/PEP (EP-05) before a call ever reaches this process.

Run directly for local development:

    python -m example_mcp_servers.sales_domain.server
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

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


def main() -> None:
    host = os.environ.get("SALES_DOMAIN_HOST", "127.0.0.1")
    port = int(os.environ.get("SALES_DOMAIN_PORT", "8100"))
    server.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
