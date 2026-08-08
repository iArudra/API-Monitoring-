"""Structured JSON logging with OpenTelemetry trace correlation.

Logs are emitted in two ways:
  1. JSON lines to stdout (readable, Docker-friendly).
  2. OTLP log records to the Collector (-> Loki) via the SDK ``LoggingHandler``,
     which automatically attaches ``trace_id`` / ``span_id`` from the active
     span context so every log correlates with a trace.
"""

import json
import logging
import os
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk._logs import LoggingHandler

SERVICE_NAME = os.environ.get("SERVICE_NAME", "centralwatch-demo-app")

# Extra attributes attached to log records (e.g. via logger.info(..., extra={...})).
_LOG_RECORD_KEYS = (
    "endpoint",
    "http.method",
    "status_code",
    "duration_ms",
    "aws.service",
    "aws.operation",
    "retry.count",
    "bucket.name",
    "table.name",
    "queue.name",
    "topic.name",
    "channel",
    "user.id",
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with trace_id/span_id injected."""

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        context = span.get_span_context()

        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service.name": getattr(record, "service_name", SERVICE_NAME),
        }

        if context.is_valid:
            payload["trace_id"] = format(context.trace_id, "032x")
            payload["span_id"] = format(context.span_id, "016x")

        for key in _LOG_RECORD_KEYS:
            value = record.__dict__.get(key)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception.type"] = record.exc_info[0].__name__
            payload["exception.message"] = str(record.exc_info[1])

        return json.dumps(payload)


def setup_logging(settings) -> None:
    """Attach a JSON stdout handler and an OTLP LoggingHandler to the root logger."""
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    root.addHandler(console)

    # Forwards log records to the Collector (-> Loki) with trace context.
    otlp_handler = LoggingHandler(level=logging.INFO)
    root.addHandler(otlp_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger that emits JSON + OTLP records."""
    return logging.getLogger(name)
