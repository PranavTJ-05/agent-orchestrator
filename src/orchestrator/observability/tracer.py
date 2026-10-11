from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    _has_otlp = True
except ImportError:
    _has_otlp = False


def setup_tracing(service_name: str = "agent-orchestrator") -> None:
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint and _has_otlp:
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


@asynccontextmanager
async def trace_span(name: str, attributes: dict | None = None) -> AsyncIterator[trace.Span]:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            span.set_attributes(attributes)
        yield span
