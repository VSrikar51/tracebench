"""Our custom OpenTelemetry exporter: writes finished spans into Postgres."""

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode
from sqlalchemy import text

from tracebench.db import engine
from tracebench.telemetry import attributes as attr

logger = logging.getLogger(__name__)

SPAN_INSERT = text("""
    INSERT INTO telemetry.spans
        (span_id, trace_id, parent_span_id, name, kind, start_time, end_time,
         status, status_message, attributes)
    VALUES
        (:span_id, :trace_id, :parent_span_id, :name, :kind, :start_time, :end_time,
         :status, :status_message, CAST(:attributes AS JSONB))
    ON CONFLICT (span_id) DO NOTHING
""")

LLM_CALL_INSERT = text("""
    INSERT INTO telemetry.llm_calls
        (span_id, trace_id, provider, model, input_tokens, output_tokens, cost_usd,
         finish_reason, input_messages, output_message)
    VALUES
        (:span_id, :trace_id, :provider, :model, :input_tokens, :output_tokens, :cost_usd,
         :finish_reason, CAST(:input_messages AS JSONB), CAST(:output_message AS JSONB))
    ON CONFLICT (span_id) DO NOTHING
""")

TOOL_CALL_INSERT = text("""
    INSERT INTO telemetry.tool_calls
        (span_id, trace_id, tool_name, call_id, arguments, result, success, error_message)
    VALUES
        (:span_id, :trace_id, :tool_name, :call_id, CAST(:arguments AS JSONB),
         CAST(:result AS JSONB), :success, :error_message)
    ON CONFLICT (span_id) DO NOTHING
""")


def hex_id(value: int, width: int) -> str:
    """Write an ID number as hex text, padded to a fixed width."""
    return format(value, f"0{width}x")


def to_datetime(nanoseconds: int) -> datetime:
    """Turn OpenTelemetry's nanosecond timestamps into a normal date and time."""
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=UTC)


def json_text(value: Any) -> str | None:
    """Turn a value into JSON text for a JSONB column. Text that's already JSON is kept as is."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            pass
    return json.dumps(value, default=str)


class PostgresSpanExporter(SpanExporter):
    """Writes each finished span to telemetry.spans, plus llm_calls or tool_calls."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        span_rows, llm_rows, tool_rows = [], [], []

        for span in spans:
            span_id = hex_id(span.context.span_id, 16)
            trace_id = hex_id(span.context.trace_id, 32)
            attributes = dict(span.attributes or {})

            span_rows.append({
                "span_id": span_id,
                "trace_id": trace_id,
                "parent_span_id": hex_id(span.parent.span_id, 16) if span.parent else None,
                "name": span.name,
                "kind": span.kind.name,
                "start_time": to_datetime(span.start_time),
                "end_time": to_datetime(span.end_time),
                "status": span.status.status_code.name.lower(),
                "status_message": span.status.description,
                "attributes": json_text({
                    key: value
                    for key, value in attributes.items()
                    if key not in attr.CONTENT_ATTRIBUTES
                }),
            })

            operation = attributes.get(attr.OPERATION_NAME)

            if operation == "chat":
                finish_reasons = attributes.get(attr.RESPONSE_FINISH_REASONS) or [None]
                llm_rows.append({
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "provider": attributes.get(attr.PROVIDER_NAME, "unknown"),
                    "model": attributes.get(attr.RESPONSE_MODEL)
                    or attributes.get(attr.REQUEST_MODEL, "unknown"),
                    "input_tokens": attributes.get(attr.USAGE_INPUT_TOKENS, 0),
                    "output_tokens": attributes.get(attr.USAGE_OUTPUT_TOKENS, 0),
                    "cost_usd": attributes.get(attr.COST_USD, 0.0),
                    "finish_reason": finish_reasons[0],
                    "input_messages": json_text(attributes.get(attr.INPUT_MESSAGES)),
                    "output_message": json_text(attributes.get(attr.OUTPUT_MESSAGES)),
                })

            elif operation == "execute_tool":
                failed = span.status.status_code == StatusCode.ERROR
                tool_rows.append({
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "tool_name": attributes.get(attr.TOOL_NAME, "unknown"),
                    "call_id": attributes.get(attr.TOOL_CALL_ID),
                    "arguments": json_text(attributes.get(attr.TOOL_CALL_ARGUMENTS)),
                    "result": json_text(attributes.get(attr.TOOL_CALL_RESULT)),
                    "success": not failed,
                    "error_message": span.status.description if failed else None,
                })

        try:
            with engine.begin() as conn:
                if span_rows:
                    conn.execute(SPAN_INSERT, span_rows)
                if llm_rows:
                    conn.execute(LLM_CALL_INSERT, llm_rows)
                if tool_rows:
                    conn.execute(TOOL_CALL_INSERT, tool_rows)
        except Exception:
            logger.exception("Could not write %d spans to Postgres", len(span_rows))
            return SpanExportResult.FAILURE

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Nothing to close: the database engine is shared with the rest of the app."""