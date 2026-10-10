# 0006. Eval dataset: generated tasks plus hand-written edge cases

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The eval dataset drives the scores, the judge calibration, and the
failure-mode dashboard. Expected outcomes must be correct, and the tasks must
cover both routine and tricky cases.

## Options considered

1. Hand-write all tasks
2. Generate tasks from templates over the seeded store data
3. Generate tasks with an LLM, then review by hand

## Decision

About 60 tasks: about 45 generated from templates (option 2) and about 15
hand-written for adversarial, ambiguous, and escalation cases.

| Category                      | Approx. count |
|-------------------------------|---------------|
| Order status lookups          | 8             |
| Refunds within policy         | 10            |
| Refunds that should be denied | 8             |
| Policy questions              | 8             |
| Inventory / restock           | 6             |
| Escalation needed             | 6             |
| Ambiguous or missing info     | 6             |
| Adversarial                   | 8             |

Each task stores the customer message, expected tool calls, the expected end
state (refund amount, escalated or not), and the policy that should be cited.

A 15-task smoke subset is used for quick iteration.

## Why

- Templates compute expected outcomes from the policy rules in code, so the
  ground truth is correct by construction and can be regenerated anytime.
- Hand-written tasks cover cases where creativity matters, such as prompt
  injection and vague requests.

## Consequences

- Templated messages read less naturally than real customer messages.
- Separately, about 30 of the agent's actual responses are labeled by hand
  (pass/fail plus failure category) to measure how well the judge agrees
  with a human.