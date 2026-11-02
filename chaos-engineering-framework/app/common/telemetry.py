"""Shared telemetry bootstrap used by every service.

Gives each service the three observability signals required by the project:
  * metrics  -> Prometheus client exposed on /metrics
  * traces   -> OpenTelemetry SDK exporting OTLP/gRPC to the OTel Collector
  * logs     -> structured JSON on stdout (picked up by Promtail -> Loki),
                carrying the active trace_id so logs and traces can be correlated
"""
import json
import logging
import os
import time

from flask import Response, g, request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "app_http_requests_total", "HTTP requests handled", ["component", "route", "status"]
)
LATENCY = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request latency",
    ["component", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


class JsonFormatter(logging.Formatter):
    def __init__(self, component):
        super().__init__()
        self.component = component

    def format(self, record):
        ctx = trace.get_current_span().get_span_context()
        return json.dumps(
            {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "component": self.component,
                "pod": os.getenv("HOSTNAME", ""),
                "msg": record.getMessage(),
                "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else "",
            }
        )


def init(component, app):
    # --- logs ---
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(component))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # --- traces ---
    provider = TracerProvider(resource=Resource.create({"service.name": component}))
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector.observability:4317")
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    FlaskInstrumentor().instrument_app(app, excluded_urls="healthz,metrics")
    RequestsInstrumentor().instrument()

    # --- metrics ---
    @app.before_request
    def _start_timer():
        g.t0 = time.perf_counter()

    @app.after_request
    def _record(resp):
        route = request.url_rule.rule if request.url_rule else "unmatched"
        if route not in ("/metrics", "/healthz"):
            REQUESTS.labels(component, route, str(resp.status_code)).inc()
            LATENCY.labels(component, route).observe(time.perf_counter() - g.get("t0", time.perf_counter()))
        return resp

    @app.route("/metrics")
    def _metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.route("/healthz")
    def _healthz():
        return "ok", 200
