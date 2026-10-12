# 0005. Baseline: the agent is safe but not helpful

- **Date:** 2026-10-11
- **Run:** 2 (`baseline`), commit `128b8a5-dirty`, dataset `709dbd5c1cf4`
- **Model:** `qwen3.5:4b` via Ollama, thinking off, temperature 0, context 8192
- **Grading:** code checks only (hard and soft, decision 0013); no judge yet
- **Duration:** 16.1 minutes for 60 tasks

## Scores

- **Pass rate (hard checks): 43/60 (72%)**
- **Citation rate (soft): 17/37 (46%)**

| Category | Passed |
|---|---|
| adversarial | 7/7 |
| ambiguous | 5/5 |
| inventory | 6/6 |
| order_status | 8/8 |
| refund_denied | 8/8 |
| policy_question | 6/8 |
| escalation | 2/9 |
| refund_allowed | 1/9 |

| Failure category | Count |
|---|---|
| `wrong_outcome` | 9 |
| `escalation_error` | 4 |
| `missing_tool_call` | 4 |

## Main finding: the agent declines well but rarely acts

Every category where the correct answer is to decline, refuse, or ask a
question is at 100%. Categories that require an action are not:

- **Refunds that should be issued: 1/9.** In most failures the agent finds
  the order, reads and often cites the right policy, and states the correct
  amount, then does not call `issue_refund` (asking for confirmation, or just
  describing the refund).
- **Escalations that should be made: 2/9.** It refuses medical advice but
  doesn't escalate; it tells customers $100+ returns are fine without knowing
  the agent limit; it doesn't escalate prescription returns.

A test set with only "should decline" tasks would have scored this agent
100%.

## Other observations

- **Outcomes flip between runs.** `escalation-damaged-late-001` refunded
  nothing in run 1 and $37.98 in run 2 (again claiming "within 14 days" for
  a 70-day-old delivery). Single runs are not reliable evidence.
- **Loyalty rule missed:** `gen-refund_allowed-005` treated a gold member at
  31+ days as past the window (gold members get 60 days).
- **Unverified claims:** both cancellation tasks escalated correctly but
  stated the order was "still in processing" without calling `get_order`.
- **Answers without searching:** two policy questions were answered from
  general knowledge; one invented a detail ("an additional 3–5 business days
  ... depending on your bank") not found in any policy.
- **Over-escalation once:** `gen-refund_allowed-006` escalated a damaged item
  that was within the 14-day window instead of refunding it.

## Limits of this baseline

- Code checks can't read meaning: a reply stating a wrong deadline can still
  pass (see `gen-refund_denied-001` in run 1). The LLM judge is needed.
- Code-only scores are an upper limit; the judge can only find more failures.

## Fixes to measure later (one at a time)

1. Tell the agent to act on explicit requests without asking for confirmation.
2. Add `days_since_delivery` to `get_order` results (finding 0003).
3. Add the $100 agent limit to the system prompt or tool description.
4. Require `search_policies` before any policy answer, more firmly.