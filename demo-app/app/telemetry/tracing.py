"""Small helpers for manual (business) spans and consistent span attributes.

Automatic instrumentation covers the vast majority of telemetry; manual spans are
used ONLY for high-value business workflows (login, order creation, image
processing, notifications, retries). Attribute names are kept consistent.
"""

from opentelemetry import trace
from opentelemetry.trace import SpanKind

_TRACER: trace.Tracer | None = None


def _tracer() -> trace.Tracer:
    global _TRACER
    if _TRACER is None:
        _TRACER = trace.get_tracer("centralwatch-demo-app.business", "1.0.0")
    return _TRACER


def business_span(name: str, attributes: dict | None = None, kind: SpanKind = SpanKind.INTERNAL):
    """Context manager for a manual business span."""
    return _tracer().start_as_current_span(name, kind=kind, attributes=attributes or {})


def aws_attributes(service: str, operation: str, attributes: dict | None = None) -> dict:
    """Build a consistent attribute set for spans that involve AWS calls."""
    attrs: dict = {
        "application.name": "centralwatch-demo-app",
        "aws.service": service,
        "aws.operation": operation,
    }
    if attributes:
        for key, value in attributes.items():
            if value is not None:
                attrs[key] = value
    return attrs


def current_traceparent() -> str | None:
    """W3C traceparent header for the current span (for cross-service propagation)."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    flags = context.trace_flags
    return f"00-{format(context.trace_id, '032x')}-{format(context.span_id, '016x')}-{flags:02x}"
