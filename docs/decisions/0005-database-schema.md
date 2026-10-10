# 0005. Database schema: span tree plus typed tables

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The database stores the pet store's data, the traces, and the eval results.
Dashboard queries need to be fast and simple, and traces need to keep their
parent/child structure.

## Options considered

1. One generic `spans` table with all details in a JSONB column
2. Only typed tables (`llm_calls`, `tool_calls`), no span tree
3. A hybrid: a generic `spans` table plus typed side tables

## Decision

One database with three Postgres schemas: `store`, `telemetry`, and `evals`.

Telemetry uses option 3:

- `telemetry.spans`: trace_id, span_id, parent_span_id, name, kind,
  start_time, end_time, duration_ms, status, attributes (JSONB)
- `telemetry.llm_calls`: span_id, model, provider, input_tokens,
  output_tokens, cost_usd, prompt, completion, finish_reason
- `telemetry.tool_calls`: span_id, tool_name, arguments (JSONB),
  result (JSONB), success, error_message

## Why

- The span tree stays faithful to OpenTelemetry, which the trace viewer needs.
- Frequently queried fields become real columns, so cost and latency queries
  are simple SQL with indexes.
- Raw attributes are still kept in full, so nothing is lost.

## Consequences

- The exporter writes to more than one table for each LLM or tool span.
- Adding a new promoted field requires a migration (Alembic).
- The app connects with its own database user, not the `postgres` superuser.