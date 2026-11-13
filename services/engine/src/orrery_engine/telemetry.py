"""Tracing, error reporting, and log correlation for the engine (requirement 11).

OpenTelemetry continues the worker's trace from the incoming `traceparent` header and exports
over OTLP/HTTP; the Sentry SDK reports unhandled errors to GlitchTip. Both are off unless their
endpoint is configured, which production requires.
"""

from collections.abc import MutableMapping
from typing import Any

import sentry_sdk
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from orrery_engine.settings import Settings


def start(settings: Settings, app: FastAPI) -> None:
    if settings.otlp_endpoint:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": "orrery-engine",
                    "deployment.environment.name": settings.environment,
                    **({"service.version": settings.release} if settings.release else {}),
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces")
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        HTTPXClientInstrumentor().instrument()
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.environment,
            release=settings.release,
            send_default_pii=False,
            traces_sample_rate=0,
        )


def add_trace_ids(
    _logger: object, _method: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: adds the active trace and span ids to each log line."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event["trace_id"] = format(context.trace_id, "032x")
        event["span_id"] = format(context.span_id, "016x")
    return event
