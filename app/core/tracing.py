from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from collections.abc import Sequence
from opentelemetry.sdk.trace import ReadableSpan


class NoOpExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> None:
        return None

    def shutdown(self) -> None:
        return None


def configure_tracing() -> None:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(NoOpExporter()))
    trace.set_tracer_provider(provider)
