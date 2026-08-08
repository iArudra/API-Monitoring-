"""Centralized OpenTelemetry setup: resource, SDK providers, exporters, auto-instrumentation.

This is the ONLY place where OpenTelemetry SDK wiring lives. Business code stays
independent of observability concerns and only uses the small helpers exposed by
``telemetry.tracing`` / ``telemetry.metrics`` / ``telemetry.logging``.
"""

import os
import socket

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _endpoint(settings) -> str:
    return settings.otel_exporter_endpoint.rstrip("/")


def _container_id() -> str:
    # Docker sets HOSTNAME to the (short) container id.
    return os.environ.get("HOSTNAME", socket.gethostname())


def build_resource(settings) -> Resource:
    """Resource attributes attached to every metric, log, and trace."""
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.environment,
            "cloud.provider": "aws",
            "cloud.region": settings.aws_region,
            "host.name": socket.gethostname(),
            "container.id": _container_id(),
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
        }
    )


def configure_telemetry(settings) -> Resource:
    """Create and install the trace/metrics/logs SDK providers with OTLP HTTP exporters.

    All three signals are sent to the existing OpenTelemetry Collector (port 4318),
    which fans them out to Prometheus (metrics), Loki (logs), and Tempo (traces).
    """
    resource = build_resource(settings)
    endpoint = _endpoint(settings)

    # --- Traces ------------------------------------------------------------
    # NOTE: the OTLP HTTP exporters use an explicitly-passed ``endpoint``
    # verbatim (they only append the signal path when resolving from env vars),
    # so the /v1/* signal paths must be appended here.
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics -----------------------------------------------------------
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=settings.otel_metrics_export_interval_ms,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Logs ----------------------------------------------------------------
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")))
    _logs.set_logger_provider(logger_provider)

    return resource


def instrument_app(app, settings) -> None:
    """Apply automatic instrumentation (FastAPI/ASGI + botocore/boto3).

    Must be called after the application middleware stack is finalized so the
    ASGI server span wraps our own request-logging middleware.
    """
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=trace.get_tracer_provider(),
        meter_provider=metrics.get_meter_provider(),
    )
    BotocoreInstrumentor().instrument()


def shutdown_telemetry() -> None:
    """Flush and shut down all SDK providers (graceful shutdown)."""
    trace.get_tracer_provider().shutdown()
    metrics.get_meter_provider().shutdown()
    _logs.get_logger_provider().shutdown()
