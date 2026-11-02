"""Slice 9: the request log line and tracing."""

import json
import logging

import pytest
from django.test import Client
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from config.observability import JsonFormatter, setup_tracing

pytestmark = pytest.mark.usefixtures("as_app_role")


def request_lines(caplog):
    return [
        json.loads(JsonFormatter().format(r)) for r in caplog.records if r.name == "schools.request"
    ]


def test_one_line_per_request_without_personal_data(alice, schools, caplog):
    caplog.set_level(logging.INFO, logger="schools.request")
    body = {"identifier": "alice@example.com", "password": "wrong"}
    Client().post(
        "/api/auth/login/?next=secret",
        body,
        content_type="application/json",
        HTTP_HOST="a.localhost",
    )
    (line,) = request_lines(caplog)
    assert line | {"time": None, "duration_ms": None} == {
        "time": None,
        "level": "info",
        "logger": "schools.request",
        "message": "request",
        "method": "POST",
        "route": "api/auth/login/",
        "status": 400,
        "duration_ms": None,
        "school_id": schools[0].pk,
        "member": False,
        "trace_id": None,
    }
    assert "alice" not in json.dumps(line) and "secret" not in json.dumps(line)


def test_traced_requests_carry_their_trace_id(schools, caplog):
    caplog.set_level(logging.INFO, logger="schools.request")
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    DjangoInstrumentor().instrument(tracer_provider=provider)
    try:
        Client().get("/api/auth/school/", HTTP_HOST="a.localhost")
    finally:
        DjangoInstrumentor().uninstrument()
    (line,) = request_lines(caplog)
    (span,) = spans.get_finished_spans()
    assert line["trace_id"] == format(span.context.trace_id, "032x")


def test_tracing_is_off_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    setup_tracing()
    assert not DjangoInstrumentor().is_instrumented_by_opentelemetry
