# 0009. Judge v2 on the dev set: too strict

- **Date:** 2026-10-21
- **Run:** 3, dev set (32 labels); test set not used
- **Judge:** `phi4-mini`, v2 (five questions about what the reply says,
  categories chosen in code)

## Results

| Dev set | v1 | v2 |
|---|---|---|
| Judge agreement | 69% | 48% |
| Judge kappa | 0.20 | 0.09 |
| Judge catch rate | 27% | 82% |
| Judge false alarm rate | 10% | 70% |
| Final (code + judge) kappa | 0.58 | 0.19 |
| Judge errors | 0 | 1 (3%) |

v2 passed 8 of 32 results; the human passed 21.

## What went wrong

Most false alarms were simple replies (inventory, order status, policy
questions) failed as `policy_violation`. Most v2 questions apply only
sometimes, and each said to answer true when it doesn't apply. The small
model kept answering false instead. Asking it both to decide whether a
question applies and to answer it was too much.

## Decision

v2 is rejected on the dev set and is not evaluated on the test set.

## Lesson

Small judge models handle conditional instructions ("if this doesn't apply,
answer true") poorly. Whether a question applies should be decided in code,
and only applicable questions asked.