# 0009. Policy search: keyword search first, hybrid search later

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The agent's `search_policies` tool must return the right policy documents for
a customer's question, so the agent can follow and cite them. There are 11
short policy documents, and development happens on a MacBook Air M2 with 8GB
of memory.

## Options considered

1. Keyword search with Postgres full-text search
2. Meaning search with embeddings and the pgvector extension
3. Hybrid search combining keyword and embedding results
4. No search: include all policies in every prompt

## Decision

Start with option 1. Upgrade to option 3 (hybrid) in a later phase.

Retrieval is measured on its own with recall@3: whether the policy each eval
task expects appears in the top 3 search results.

## Why

- Full-text search is built into Postgres: no extra model, no extra memory,
  and nothing new to install.
- Postgres handles word forms (e.g., "returned", "returns", "returning").
- Measuring recall@3 before and after the upgrade turns the switch to hybrid
  search into a data-driven result for the README.
- Including all policies in every prompt would slow every LLM call on the
  local model and remove retrieval from the project.

## Consequences

- Keyword search misses synonyms (e.g., "broken" or "ripped" vs. "damaged").
  These misses are expected and become the baseline for the hybrid upgrade.
- The hybrid upgrade needs the pgvector extension, which requires a one-time
  setup as the `postgres` superuser, and a small local embedding model.
- Policies are stored in a `store.policies` table so both search methods can
  run over the same data.