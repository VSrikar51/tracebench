# tracebench

Tracing and evaluation platform for LLM agents.

> **Work in progress**: being built step by step.

## What it does

tracebench watches an AI customer-support agent for a fictional pet store,
records every step it takes, and grades how well it did.

- **Tracing**: every LLM call and tool call is recorded with OpenTelemetry
  and stored in PostgreSQL, including tokens, cost, and latency.
- **Evaluation**: answers are graded by code-based checks plus an
  LLM-as-judge, and the judge is checked against human labels.
- **Dashboards**: Grafana shows failure modes, cost, and latency per step.

## Tech stack

Python 3.12 · uv · OpenTelemetry · PostgreSQL · Ollama · Grafana · Streamlit

## Status

- [x] Project setup
- [x] Pet store data and policy search
- [x] Agent
- [x] Tracing
- [ ] Eval harness
- [ ] Dashboards