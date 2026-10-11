# 0011. Trace content: record conversation text on spans, behind a switch

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

Every span records metadata (timing, tokens, model, tool name). The question
is whether spans should also record content: customer messages, model
replies, and tool inputs and results.

The OpenTelemetry GenAI semantic conventions (status: Development, now
maintained in their own repository) say instrumentation should not capture
content by default, because it is often sensitive and large, but should let
users opt in. They describe three patterns: no content (default), content on
span attributes (suited to pre-production), and content in external storage
with references on spans (recommended for production).

## Options considered

1. Metadata only
2. Content recorded on spans, opt-in
3. Content stored externally, with references on spans

## Decision

Option 2, controlled by a `trace_content` setting (default: on).

## Why

- All data in this project is synthetic (`@example.com` customers), so there
  is no real personal data to protect.
- The LLM judge, the labeling app, and debugging all need the content.
- Keeping it behind a switch follows the spec's opt-in guidance.

## Consequences

- Trace tables grow faster; acceptable at this project's scale.
- The OTel Collector upgrade (decision 0004) adds a PII redaction step, so
  content is scrubbed before storage in that pipeline.
- GenAI attribute names may still change, so they are kept in one module.