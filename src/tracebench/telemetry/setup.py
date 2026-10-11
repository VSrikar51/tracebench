"""Turn on tracing: create the tracer provider and connect our Postgres exporter."""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tracebench.telemetry.exporter import PostgresSpanExporter

_provider: TracerProvider | None = None


def setup_tracing() -> TracerProvider:
    """Set up tracing once. Calling it again just returns the existing setup."""
    global _provider
    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": "tracebench"}))
        _provider.add_span_processor(BatchSpanProcessor(PostgresSpanExporter()))
        trace.set_tracer_provider(_provider)
    return _provider


def get_tracer() -> trace.Tracer:
    """The pen our code uses to write spans."""
    return trace.get_tracer("tracebench")


if __name__ == "__main__":
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from sqlalchemy import text

    from tracebench.db import engine
    from tracebench.telemetry import attributes as attr

    provider = setup_tracing()
    tracer = get_tracer()

    with tracer.start_as_current_span("invoke_agent demo") as root:
        root.set_attribute(attr.OPERATION_NAME, "invoke_agent")

        with tracer.start_as_current_span("chat demo-model", kind=SpanKind.CLIENT) as span:
            span.set_attribute(attr.OPERATION_NAME, "chat")
            span.set_attribute(attr.PROVIDER_NAME, "ollama")
            span.set_attribute(attr.REQUEST_MODEL, "demo-model")
            span.set_attribute(attr.USAGE_INPUT_TOKENS, 120)
            span.set_attribute(attr.USAGE_OUTPUT_TOKENS, 15)
            span.set_attribute(attr.RESPONSE_FINISH_REASONS, ["stop"])

        with tracer.start_as_current_span("execute_tool get_order") as span:
            span.set_attribute(attr.OPERATION_NAME, "execute_tool")
            span.set_attribute(attr.TOOL_NAME, "get_order")
            span.set_status(Status(StatusCode.ERROR, "No order 9999 found"))

        trace_id = format(root.get_span_context().trace_id, "032x")

    provider.force_flush()

    with engine.begin() as conn:
        params = {"trace_id": trace_id}
        print(f"Trace {trace_id}\n")

        spans = conn.execute(text("""
            SELECT name, kind, status, round(duration_ms::numeric, 2) AS ms,
                   parent_span_id IS NULL AS is_root
            FROM telemetry.spans
            WHERE trace_id = :trace_id
            ORDER BY start_time
        """), params).mappings().all()
        for row in spans:
            indent = "" if row["is_root"] else "  └─ "
            print(f"{indent}{row['name']}  [{row['kind']}, {row['status']}, {row['ms']} ms]")

        llm = conn.execute(text("""
            SELECT model, input_tokens, output_tokens FROM telemetry.llm_calls
            WHERE trace_id = :trace_id
        """), params).mappings().all()
        print(f"\nllm_calls:  {[dict(row) for row in llm]}")

        tools = conn.execute(text("""
            SELECT tool_name, success, error_message FROM telemetry.tool_calls
            WHERE trace_id = :trace_id
        """), params).mappings().all()
        print(f"tool_calls: {[dict(row) for row in tools]}")

        conn.execute(text("DELETE FROM telemetry.spans WHERE trace_id = :trace_id"), params)
        left = conn.execute(text(
            "SELECT count(*) FROM telemetry.llm_calls WHERE trace_id = :trace_id"
        ), params).scalar_one()
        print(f"\nDemo trace deleted. llm_calls rows left (should be 0): {left}")