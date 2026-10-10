# 0002. Agent loop: custom Python loop

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The agent needs a loop that sends messages to a model, receives tool calls,
runs the tools, and repeats until it has a final answer. The way we build this
loop decides how much control we have over tracing.

## Options considered

1. Our own loop in Python on top of the model provider's SDK
2. LangGraph
3. An agent SDK with built-in tracing (e.g., the OpenAI Agents SDK)

## Decision

Option 1: Python 3.12, our own loop (about 150–200 lines), Pydantic models for
tool schemas, and a thin provider wrapper so models can be swapped.

## Why

- We control exactly where every span starts and ends, which is the core of
  this project.
- Every line can be explained in an interview; nothing is hidden by a framework.
- LangGraph's tracing usually goes through LangSmith, and agent SDKs come with
  tracing built in. Both would hide the instrumentation work this project is
  meant to show.
- The provider wrapper makes it possible to compare models on cost and quality.

## Consequences

- We write and maintain retry logic, step limits, and error handling ourselves.
- No ready-made graph features like checkpointing; we don't need them here.