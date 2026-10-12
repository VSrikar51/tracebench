# 0013. Hard and soft code checks

- **Status:** Accepted
- **Date:** 2026-10-11
- **Supersedes:** the pass rule in [0007](0007-judge-rubric.md)

## Context

Decision 0007 said a task passes only if every code check passes. The first
smoke run (run 1, 8/14) showed this mixes serious mistakes with formatting:
two tasks with correct behavior (refusing a privacy probe, escalating a
prescription return) failed only because the reply didn't include a
`[policy-id]` citation. They counted the same as a reply that gave a
customer a wrong return deadline.

## Options considered

1. Keep every code check required for a pass
2. Split checks into hard checks (decide pass/fail) and soft checks
   (scored separately)
3. Remove citation checks and leave policy compliance to the judge

## Decision

Option 2.

- **Hard checks** decide whether a task passes: the agent finished, the
  refund amount, escalation, required tools, and forbidden tools. The
  question they answer: did the customer get the right outcome?
- **Soft checks** are scored separately: policy citations, reported as a
  citation rate across all tasks that need one.
- The primary failure category comes only from failed hard checks (and,
  once added, the judge).

## Why

- The headline score means one specific thing: the right outcome for the
  customer.
- Citation data is still collected, so prompt changes that affect citing can
  be measured.

## Consequences

- Run reports show two numbers: the pass rate and the citation rate.
- A task can pass with missing citations; those show up in the citation rate
  rather than the pass rate.
- Judging the reply's meaning (e.g., a wrong deadline stated in words) is
  still the judge's job.