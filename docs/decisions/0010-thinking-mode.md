# 0010. Thinking mode: off by default

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The local agent model, `qwen3.5:4b`, has a thinking mode: it writes out its
reasoning before answering. Each agent task makes about 5 model calls, and a
full eval run has about 60 tasks.

Measured on a MacBook Air M2 (8GB), for the same short question:

| Mode         | Tokens written | Total time |
|--------------|----------------|------------|
| Thinking on  | 952            | 42.5 s     |
| Thinking off | 54             | 4.8 s      |

Both runs used 100% GPU at about 24 tokens/s.

## Options considered

1. Thinking on for every model call
2. Thinking off for every model call
3. Thinking off by default, with a setting to turn it on

## Decision

Option 3. Thinking is off by default and can be turned on in `config.yaml`.

## Why

- Thinking made a short answer about 9 times slower. With thinking on, a full
  eval run would take more than 3 hours.
- Keeping it as a setting allows a later experiment: run the same eval tasks
  with thinking on and off, and compare pass rate against latency and tokens.

## Consequences

- The agent may make more reasoning mistakes on tricky tasks with thinking
  off. The eval results will show how much this matters.
- The model's context window must be raised from the default 4096 tokens to
  8192 to fit the agent's instructions, tool descriptions, and conversation.