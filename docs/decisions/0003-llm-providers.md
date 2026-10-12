# 0003. LLM providers: local-first hybrid

- **Status:** Accepted; the local judge model is superseded by [0014](0014-judge-model.md)
- **Date:** 2026-10-09

## Context

The agent and the judge both need language models. The budget for paid APIs
is at most $5 per provider, and development happens on a MacBook Air M2 with
8GB of memory.

## Options considered

1. One paid provider for both the agent and the judge
2. A cheap paid model for the agent and a stronger model from a different
   provider for the judge
3. Local models only, through Ollama
4. A hybrid: local models by default, paid models optional for final results

## Decision

Option 4.

- Local agent model: `qwen3.5:4b` (fallback: `llama3.2:3b`)
- Local judge model: `gemma4:e4b` (a different model family from the agent)
- Optional paid setup: a cheap Anthropic model for the agent and an OpenAI
  model for the judge, added only when needed
- Model names and per-token prices live in `config.yaml`, not in code

## Why

- Development costs nothing, and the project runs end to end without any API
  keys, so anyone can clone and run it.
- Using a judge from a different model family than the agent avoids
  self-preference bias.
- Paid models can still produce the final numbers for the README, including a
  local vs. paid comparison.

## Consequences

- A budget guard stops runs before spending passes a cap (e.g., $4.50 per
  provider), using the cost data already captured in traces.
- Small local models fail more often. This is useful, because the failure-mode
  analysis needs failures to study.
- Memory is tight: the agent and judge models never run at the same time,
  Postgres runs natively instead of in Docker during development, and eval
  runs take roughly 30–60 seconds per task.
- The CI eval gate can't host a local model, so it replays recorded LLM
  responses instead of calling models.