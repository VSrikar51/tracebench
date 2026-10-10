# 0001. Agent domain: pet store customer support

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

tracebench needs a multi-step agent to trace and evaluate. The agent's domain
decides how easy it is to check whether its answers are right, which matters
because the evals are the core of the project.

## Options considered

1. A customer support agent for a fictional online pet store
2. A document Q&A agent over contracts or policy documents
3. A data analyst agent that writes SQL against a sample database

## Decision

Option 1, plus a policy search tool borrowed from option 2.

The agent's tools are `get_customer`, `get_order`, `check_inventory`,
`search_policies`, `issue_refund`, and `escalate_to_human`.

## Why

- Most answers can be checked by code, such as whether the refund amount or
  order status is correct. That gives reliable ground truth for the evals.
- Support agents fail in clear, nameable ways: wrong tool, wrong refund,
  missed escalation. That makes the failure-mode dashboard meaningful.
- Policy search adds retrieval and citations, which covers the document Q&A
  use case without giving up checkable answers.
- All data is synthetic, so there are no privacy concerns.

## Consequences

- We must build seed data (customers, orders, products) and about 10–15
  short policy documents.
- Answers to policy questions are harder to check with code, so those rely
  more on the LLM judge.