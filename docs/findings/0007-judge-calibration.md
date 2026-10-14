# 0007. Judge calibration: the local judge makes grading worse

- **Date:** 2026-10-14
- **Run:** 3 (`baseline`), dataset `46350a22d36d`
- **Judge:** `phi4-mini`, prompt v1 (five yes/no questions)
- **Labels:** 32 results (stratified sample, seed 7), labeled blind by one
  person; human pass rate 21/32 (66%)

## Results

| Grader | Agreement | Kappa | Catch rate | False alarm rate |
|---|---|---|---|---|
| Code checks | 84% | 0.63 (substantial) | 64% | 5% |
| Judge | 69% | 0.20 (fair) | 27% | 10% |
| Final (code + judge) | 81% | 0.58 (moderate) | 73% | 14% |

When both the human and the final grade failed a result, the failure category
matched 6/8 times.

## Main finding

Adding the judge lowered agreement with the human labels (kappa 0.63 → 0.58):
it caught one extra real failure but added two false alarms. An uncalibrated
LLM judge made grading worse.

## Patterns in the 10 judge disagreements

1. **Judges how the reply sounds, not what was done (5 misses).** In all five
   `refund_allowed` misses, the agent reasoned correctly and stated the right
   amount but only offered the refund. `issue_refund` was absent from the tool
   calls shown to the judge, yet it passed them. Code checks already catch
   these exactly.
2. **Misses meaning-level failures (3 misses).** It passed the fake-manager and
   split-refund near-misses (misstated limits, promised to proceed) and a reply
   with a wrong day count and a promised escalation that never happened. These
   are the failures only a reader can catch.
3. **Self-contradiction (2 false alarms).** For `ambiguous-which-kibble-001`
   and `gen-order_status-005`, the judge's reasoning said the reply was correct,
   but its answers failed it.

## Other observations from labeling

- Code checks rated all adversarial tasks as passing; human review failed 2 of
  the 4 labeled, as near-misses that a second message would likely exploit.
  Single-turn evals overstate safety.
- The agent misjudges number comparisons as well as dates (e.g., "$179.98 is
  under the $100 limit").
- Some replies make unnecessary tool calls (e.g., `check_inventory` during a
  refund).
- One task is flawed: a shipped-order refund task whose order contains
  prescription food, which the generator didn't account for.

## What this motivates

- Narrow the judge to what code can't check (facts, stated rules, promises)
  and give it facts computed in code, then re-measure against the same labels.
- Keep the code-check score as the headline until the judge is shown to help.
- Consider multi-turn adversarial tasks.
- **Caution:** improving the judge against these 32 labels risks tuning it to
  them. A second, fresh batch of labels is needed to confirm any improvement.