"""Example Finance-domain MCP server (EP-06-T03).

invoice.get (R1, read-only), payment.create (R2, side-effecting, not yet
executed), payment.execute (R3, high-impact -- REQUIRE_APPROVAL above
Finance.Payments' `restrictions.approval_threshold`, enforced entirely by
config/policies/transaction.rego before the call ever reaches here). Backed
by static mock data -- this server is deliberately "dumb" (ADR-023): it never
authorizes anything, only the Gateway/PDP does that, upstream of this process.

Run directly for local development:

    python -m example_mcp_servers.finance_domain.server
"""

from __future__ import annotations

import itertools
import os

from mcp.server.mcpserver import MCPServer
from starlette.types import ASGIApp

from emcp_bus.audit.bypass_detection import BackendCredentialGate
from emcp_bus.audit.sink import JSONLFileAuditSink
from emcp_bus.common.otel import setup_tracing

setup_tracing("finance-domain-mcp-server")

server = MCPServer(name="finance-domain", version="0.1.0")

_INVOICES: dict[str, dict[str, object]] = {
    "inv-001": {
        "invoice_id": "inv-001",
        "customer_id": "cust-001",
        "amount": 5000,
        "status": "open",
    },
    "inv-002": {
        "invoice_id": "inv-002",
        "customer_id": "cust-002",
        "amount": 25000,
        "status": "overdue",
    },
}

_PAYMENTS: dict[str, dict[str, object]] = {}
_payment_ids = itertools.count(1)


@server.tool(name="finance.invoice.get", description="Get a single finance invoice by id.")
def invoice_get(invoice_id: str) -> dict[str, object]:
    invoice = _INVOICES.get(invoice_id)
    if invoice is None:
        return {"error": "not_found", "invoice_id": invoice_id}
    return invoice


@server.tool(
    name="finance.payment.create", description="Create a draft payment against an invoice."
)
def payment_create(invoice_id: str, amount: float) -> dict[str, object]:
    payment_id = f"pay-{next(_payment_ids):03d}"
    payment = {
        "payment_id": payment_id,
        "invoice_id": invoice_id,
        "amount": amount,
        "status": "draft",
    }
    _PAYMENTS[payment_id] = payment
    return payment


@server.tool(name="finance.payment.execute", description="Execute a previously created payment.")
def payment_execute(payment_id: str, amount: float) -> dict[str, object]:
    """`amount` is declared by the caller (not re-derived from the stored
    payment) so it is visible to `config/policies/transaction.rego`'s
    `approval_threshold` check (README.md §26) -- the transaction policy
    inspects call arguments, never backend state, matching `sales.quote.create`'s
    same pattern (EP-06-T02)."""
    payment = _PAYMENTS.get(payment_id)
    if payment is None:
        return {"error": "not_found", "payment_id": payment_id}
    payment["status"] = "executed"
    payment["executed_amount"] = amount
    return payment


def main() -> None:
    host = os.environ.get("FINANCE_DOMAIN_HOST", "127.0.0.1")
    port = int(os.environ.get("FINANCE_DOMAIN_PORT", "8101"))
    expected_token = os.environ.get("FINANCE_DOMAIN_SERVICE_TOKEN")
    audit_log_path = os.environ.get("EMCP_AUDIT_LOG_PATH", "/tmp/emcp-audit.jsonl")

    app: ASGIApp = server.streamable_http_app(host=host)
    if expected_token:
        # EP-05-T07: reject anything that didn't come through the Gateway's
        # outbound identity (EP-07-T01) with the matching service credential.
        app = BackendCredentialGate(
            app,
            expected_token=expected_token,
            backend="finance-domain",
            audit_sink=JSONLFileAuditSink(audit_log_path),
        )

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
