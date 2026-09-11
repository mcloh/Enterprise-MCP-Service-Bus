"""Minimal OpenTelemetry tracing setup shared by every RI service.

Walking-skeleton scope (EP-08-T01): a `TracerProvider` per process, exporting
to stdout by default so the M0 trace is visible without a running collector.
Setting `OTEL_EXPORTER_OTLP_ENDPOINT` switches to OTLP/HTTP (requires the
`emcp-bus[otlp]` extra) for use against the collector in EP-08-T04.

Trace context propagates across the gateway -> downstream MCP server hop via
the `mcp` SDK's built-in `OpenTelemetryMiddleware` (on by default on every
`Server`/`MCPServer`): it injects/extracts standard W3C `traceparent` into the
JSON-RPC `_meta` field around every request, so a single trace_id spans both
processes without any extra instrumentation here -- this is the concrete,
checkable form of the M0 acceptance criterion in docs/RI-PLANNING.md ("um
único trace_id conecta Gateway -> Fabric -> backend mock"), verified in
tests/e2e/test_walking_skeleton.py.

`setup_tracing` registers one *process-global* TracerProvider via
`opentelemetry.trace.set_tracer_provider`, which OTel only ever honors once
per process -- a second call from a different service name in the same
process is silently ignored by the OTel API itself. That is correct for the
real deployment (one service per process); tests that run two RI services
in-process (as tests/e2e/test_walking_skeleton.py does, for speed) must not
rely on `resource.attributes["service.name"]` to tell spans from different
services apart, since both end up sharing whichever provider registered
first -- use `span.kind` / `span.name` instead.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Tracer

_configured_services: set[str] = set()


def setup_tracing(service_name: str) -> Tracer:
    """Configure (once per process) a TracerProvider for `service_name` and return its Tracer.

    Idempotent: calling this more than once for the same service name in the
    same process returns a Tracer against the already-configured provider
    instead of registering a second one.
    """
    if service_name not in _configured_services:
        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            # Imported lazily: the OTLP exporter is an optional dependency
            # (`emcp-bus[otlp]`) not required for the console-only M0 path.
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
        else:
            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _configured_services.add(service_name)

    return trace.get_tracer(service_name)
