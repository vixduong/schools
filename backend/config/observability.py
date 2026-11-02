"""App-side observability (docs/slices/slice-9.md): one JSON log line per request, and
OpenTelemetry traces exported only when OTEL_EXPORTER_OTLP_ENDPOINT is set. The collector (Grafana
Alloy) and alerts come with the first infrastructure spike."""

import json
import logging
import os
import time
import traceback
from datetime import UTC, datetime

from opentelemetry import trace

# Only these fields leave the process: no identifiers, names, bodies or query strings.
REQUEST_FIELDS = ("method", "route", "status", "duration_ms", "school_id", "member", "trace_id")

log = logging.getLogger("schools.request")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            **{f: getattr(record, f) for f in REQUEST_FIELDS if hasattr(record, f)},
        }
        if record.exc_info and record.exc_info[0]:
            # Type and traceback, not the message: a database error's DETAIL can quote an email.
            kind, _, tb = record.exc_info
            line["exception"] = f"{kind.__module__}.{kind.__qualname__}\n" + "".join(
                traceback.format_tb(tb)
            )
        return json.dumps(line, ensure_ascii=False)


class RequestLogMiddleware:
    """Outermost: times the whole request, including the School's transaction."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        school = getattr(request, "school", None)
        user = getattr(request, "user", None)
        span = trace.get_current_span().get_span_context()
        log.info(
            "request",
            extra={
                "method": request.method,
                # The URL pattern, so ids and query strings stay out of the logs.
                "route": match.route if match else None,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "school_id": school.pk if school else None,
                "member": bool(user and user.is_authenticated),
                "trace_id": format(span.trace_id, "032x") if span.is_valid else None,
            },
        )
        return response


def setup_tracing() -> None:
    """Instrument Django and psycopg and export OTLP over HTTP, when an endpoint is configured
    (the standard OTEL_* variables set the endpoint, headers and service name)."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service = os.environ.get("OTEL_SERVICE_NAME", "schools-api")
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument()
    # Query text only: parameters (names, identifiers) are not captured, psycopg's default.
    PsycopgInstrumentor().instrument()
