from __future__ import annotations

from contextlib import contextmanager
from typing import Any

_TRACER = None
_CONFIGURED = False


def configure_tracing(
    *,
    enabled: bool,
    service_name: str = "novaadapt-core",
    exporter_endpoint: str | None = None,
) -> bool:
    global _TRACER, _CONFIGURED
    if not enabled:
        return False
    if _CONFIGURED and _TRACER is not None:
        return True
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return False

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter_kwargs: dict[str, Any] = {}
    if exporter_endpoint:
        exporter_kwargs["endpoint"] = exporter_endpoint
    exporter = OTLPSpanExporter(**exporter_kwargs)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)
    _CONFIGURED = True
    return True


@contextmanager
def start_span(name: str, *, attributes: dict[str, Any] | None = None):
    if _TRACER is None:
        yield None
        return
    with _TRACER.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(str(key), value)
        yield span
