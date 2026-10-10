# 0008. Dashboards: Grafana, Jaeger, and a Streamlit labeling app

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The project needs to show failure modes, cost and latency per step
(p50/p95), eval scores across runs, and single-trace drill-down. It also
needs a way to label agent responses by hand.

## Options considered

1. Streamlit for everything
2. Grafana dashboards on Postgres, plus a small Streamlit labeling app
3. A custom React/Next.js frontend with a FastAPI backend

## Decision

Option 2:

- **Grafana** for metrics dashboards, with panels as SQL over Postgres and
  dashboards saved as JSON in the repo
- **Jaeger** for single-trace drill-down, arriving with the Collector upgrade
- **Streamlit** only for the internal human-labeling tool

## Why

- Each tool does what it's used for in industry, which makes the
  architecture realistic and easy to defend.
- Dashboards as code are reviewable in the repo.
- A custom frontend would take a week or more away from the tracing and
  eval work.

## Consequences

- Grafana runs natively on the Mac via Homebrew.
- Until the Collector upgrade, trace drill-down is limited to Grafana tables.
- Three UIs to run locally; the Makefile will start them with simple commands.