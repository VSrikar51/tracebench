# 0015. Judge development protocol: dev set, sealed test set, pre-registered criteria

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

Calibration (finding 0007) showed the local judge lowers grading quality.
Improving the judge by repeatedly checking it against the same human labels
risks overfitting: a judge tuned to match those labels without getting better
at judging new results.

## Decision

Human labels for run 3 are split by task:

- **Dev set:** the 32 already-labeled results (stratified sample, seed 7).
  Used freely to develop and compare judge versions.
- **Test set:** the other 28 results of run 3, which come from different tasks.
  Labeled before any judge changes, with the labeling guide frozen. Used
  exactly once, to evaluate the single judge version chosen on the dev set.

Planned judge changes, compared on the dev set only:

- **v2:** a narrower job. The judge checks only what code can't: stated facts,
  stated rules, promises versus actions taken, and firmness of refusals.
- **v3:** v2 plus a fact sheet computed in code (e.g., days since delivery,
  return window, refund issued or not), so the judge does no arithmetic.

Judge changes must be general principles. No instructions may refer to
specific tasks, customers, orders, or products from either set.

## Success criteria (fixed before seeing any test-set results)

On the **test set**, the chosen judge is adopted for the headline score only if:

1. The final grade (code + judge) has a **higher Cohen's kappa** than code
   checks alone, and
2. The final grade's **false alarm rate is 10% or lower**.

If either fails, the code-check score remains the headline, and the result is
reported as is, including any gap between dev and test performance.

## Consequences

- The test set is labeled now, before judge development.
- Test-set calibration results are not viewed until the final evaluation.
- A dev/test gap is reported as overfitting, not hidden.
- One labeler only; agreement between multiple labelers is not measured.

## Known limitation

The dev/test split was created after the run 3 report had already printed
every failing result, including some now in the test set. Those replies were
read before the split, and the general patterns behind judge v2 were partly
drawn from them. The test labels and the judge's agreement with them were not
seen. To limit the effect, judge prompts contain only general principles and
no references to specific tasks, customers, orders, or amounts. The success
criteria above are unchanged.