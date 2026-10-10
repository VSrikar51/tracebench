# 0004. Tracing pipeline: direct exporter first, then OTel Collector

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Every LLM call and tool call must be recorded as a trace and stored in
PostgreSQL. The pipeline should reflect how production systems work without
putting the rest of the project at risk.

## Options considered

1. OpenTelemetry SDK with a custom exporter that writes directly to Postgres
2. OpenTelemetry SDK → OTel Collector → ingest service → Postgres
3. Hand-rolled tracing without OpenTelemetry

## Decision

Build option 1 first, then upgrade to option 2 in week 2.

Spans follow OpenTelemetry's GenAI semantic conventions
(e.g., `gen_ai.request.model`, `gen_ai.usage.input_tokens`).

## Why

- The direct exporter gets traces into tables within a day or two, so the
  agent, evals, and dashboards can be built on a working base.
- The Collector is the production pattern, and it adds real value here:
  PII redaction of customer data and fan-out to Jaeger for trace viewing.
- The exporter is chosen in configuration, so the switch to OTLP is a small
  change.
- If time runs short, the project still has a complete, working pipeline.

## Consequences

- The Collector has no built-in Postgres output, so the upgrade includes a
  small ingest service (FastAPI) that receives OTLP data and writes it to
  Postgres.
- The Collector runs natively as a single binary to save memory.
- The migration itself becomes a story for the README: what changed and why.