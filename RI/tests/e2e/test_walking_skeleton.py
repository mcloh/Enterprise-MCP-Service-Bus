"""M0 walking skeleton, now exercised through M1's real enforcement chain
(docs/RI-PLANNING.md, Marco M0 + M1: EP-01/EP-03/EP-04/EP-05).

Client -> Gateway (real OIDC auth + real OPA-backed entitlement) -> (static
routing) -> example Sales MCP server -> response, over real HTTP
(streamable-http), with a single OTel trace_id correlating spans across both
processes. Authenticates as `sales-read-agent` (Sales.Read, README.md §7.1)
calling only tools within its own entitlement -- the denial paths (no token,
wrong tool, expired/forged token, PDP down) are tests/e2e/test_governed_gateway.py.
"""

from __future__ import annotations

from collections.abc import Callable

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from tests.e2e.conftest import run_against_gateway

SALES_READ_CLIENT_ID = "sales-read-agent"


async def test_tools_list_is_filtered_to_sales_read_entitlement(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(lambda session: session.list_tools(), token=token)

    # README.md §7.1: Sales.Read sees exactly these four -- not
    # sales.quote.create/update (Sales.Write-only) and not any Finance tool.
    assert {tool.name for tool in result.tools} == {
        "sales.customer.search",
        "sales.customer.get",
        "sales.order.get",
        "sales.inventory.check",
    }


async def test_tools_call_reaches_the_backend_and_returns_its_result(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    token = sign_token(SALES_READ_CLIENT_ID)

    result = await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
        token=token,
    )

    assert result.is_error is not True
    assert result.structured_content == {
        "customer_id": "cust-001",
        "name": "Aurora Ltda",
        "region": "BR-SP",
    }


async def test_a_single_trace_id_correlates_gateway_and_backend_spans(
    governed_stack: None, sign_token: Callable[..., str]
) -> None:
    """Both hops of one `tools/call` must land on the same trace_id.

    This test runs both server processes in-process (in-process uvicorn, for
    speed), so they share one OTel global TracerProvider/resource -- unlike a
    real multi-process deployment (verified manually: each process gets its
    own `service.name` resource), so `resource.attributes["service.name"]`
    cannot be used here to tell the two hops apart. `SpanKind.SERVER` can:
    the gateway receiving the call from the client, and the Sales server
    receiving it from the gateway, are each a distinct SERVER-kind
    `tools/call ...` span -- exactly two (or more, under a rare transport
    retry -- see `run_against_gateway`) of them sharing one trace_id proves
    the request was correlated across both hops.
    """
    from opentelemetry import trace

    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore[attr-defined]

    token = sign_token(SALES_READ_CLIENT_ID)
    await run_against_gateway(
        lambda session: session.call_tool("sales.customer.get", {"customer_id": "cust-001"}),
        token=token,
    )

    spans: tuple[ReadableSpan, ...] = exporter.get_finished_spans()
    server_tool_call_spans = [
        span
        for span in spans
        if span.name.startswith("tools/call") and span.kind == SpanKind.SERVER
    ]
    trace_ids = {span.context.trace_id for span in server_tool_call_spans}

    assert len(trace_ids) == 1, (
        "Expected exactly one trace_id shared by both hops, got "
        f"{[f'{t:#x}' for t in trace_ids]} across spans {[s.name for s in server_tool_call_spans]}"
    )
    assert len(server_tool_call_spans) >= 2, (
        "Expected at least one SERVER 'tools/call' span for the gateway hop and one "
        f"for the backend hop, got {len(server_tool_call_spans)}: "
        f"{[s.name for s in server_tool_call_spans]} -- see Marco M0 acceptance "
        "criterion in docs/RI-PLANNING.md"
    )
