# 0014. Local judge model: phi4-mini

- **Status:** Accepted
- **Date:** 2026-10-11
- **Supersedes:** the local judge model in [0003](0003-llm-providers.md)

## Context

Decision 0003 chose `gemma4:e4b` as the local judge. In practice, that Ollama
tag is an 8.1B-parameter model with vision and audio, 9.5 GB on disk, using
`nvfp4` quantization. Ollama reported it needed 8.8 GiB of memory, while the
MacBook Air M2 (8GB) has about 4.8 GiB available for models. The "E4B" name
refers to effective parameters, not the real size.

## Options considered

1. `phi4-mini` (Microsoft, 3.8B)
2. `llama3.2:3b` (Meta, 3B)
3. `gemma3:4b` (Google, previous generation; borderline on memory)

## Decision

Option 1: `phi4-mini`, with `llama3.2:3b` as the fallback.

## Why

- Fits in memory alongside an 8,192-token context.
- A different model family from the agent (Qwen), so self-preference bias is
  still avoided.
- Microsoft's small models are trained heavily on reasoning, which suits a
  judge that must check dates and amounts.

## Consequences

- A small local judge will make mistakes. Calibration against human labels
  measures how many.
- If agreement is too low, a paid judge (decision 0003's optional paid setup)
  is used for final reported results.
- Model sizes must be checked with `ollama show` before adopting a model,
  not inferred from names.