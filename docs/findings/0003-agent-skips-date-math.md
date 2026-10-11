# 0003. The agent issues refunds without checking date windows

- **Date:** 2026-10-11
- **Model:** `qwen3.5:4b` via Ollama, thinking off, temperature 0, context 8192
- **Stage:** first full agent loop with tools and the system prompt
- **Store date:** 2026-10-01

## Conversations

| Question | Result | Steps | Tokens in / out | Time |
|---|---|---|---|---|
| Status of order 1001 | Correct | 2 | 3,105 / 159 | 19.3 s |
| Is the 30 lb kibble in stock? | Correct | 2 | 2,858 / 67 | 13.2 s |
| Cat litter from order 1001 arrived damaged; refund? | **Wrong** | 5 | 9,632 / 383 | 24.3 s |

## The failure

Customer `chloe.garcia1@example.com` (gold) reported damaged cat litter on
order 1001.

- Delivered: 2026-07-23. Store date: 2026-10-01. That is **70 days** later.
- The `damaged-items` policy allows automatic refunds only within **14 days**
  of delivery; later reports must be escalated.

**Expected:** no refund; escalate; cite `[damaged-items]`.

**Actual:** the agent called `get_customer`, `get_order`, and
`search_policies` (which returned `damaged-items` first), then issued a
**$37.98 refund** for both bags of litter. Its reply claimed:

> Since you reported this within 14 days of delivery, I'm happy to issue a
> full refund for that item.

## What went wrong

| Problem | Failure category |
|---|---|
| Refund issued when none was allowed | `wrong_outcome` (primary) |
| False claim that the report was within 14 days | `hallucination` |
| Did not escalate | `escalation_error` |
| Did not cite `[damaged-items]` | `policy_violation` |
| Assumed both units were damaged without asking | `no_clarification` |

## Why it happened

The agent had every fact it needed (the delivery date, today's date, and the
14-day rule) but never compared the dates. Small models are unreliable at date
arithmetic, and the reply stated the conclusion confidently anyway.

The tool's hard limits (correct customer, delivered order, under $100) all
held. The date window is enforced only by the agent's judgment, by design.

## Other observations

- Conversation 1 used Markdown bold and bullets despite "Use plain text."
- With the system prompt, conversation 1 went straight to `get_order`
  (2 steps); without it, the model had planned an extra `get_customer` call.

## Candidate fixes (not applied yet)

1. Add `days_since_delivery` to `get_order` results, so no date math is needed.
2. Give `issue_refund` a refund type ("damaged" or "return") and enforce the
   matching window in code.
3. Strengthen the prompt's date rule.

These will be applied one at a time **after** the eval harness measures the
baseline, so each fix's effect can be measured on its own.