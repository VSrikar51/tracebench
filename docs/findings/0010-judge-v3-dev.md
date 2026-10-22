# 0010. Judge v3 on the dev set: chosen for the test

- **Date:** 2026-10-21
- **Run:** 3, dev set (32 labels); test set not yet used
- **Judge:** `phi4-mini`, v3 (questions chosen in code, phrased as "is there a
  problem?", answered with evidence, plus a fact sheet computed in code)

## Results

| Dev set | v1 | v2 | v3 |
|---|---|---|---|
| Judge kappa | 0.20 | 0.09 | 0.63 |
| Judge catch rate | 27% | 82% | 64% |
| Judge false alarm rate | 10% | 70% | 5% |
| Final (code + judge) kappa | 0.58 | 0.19 | 0.65 |
| Final false alarm rate | 14% | 67% | 10% |
| Judge errors | 0 | 1 | 0 |

Code checks alone: kappa 0.63, false alarm rate 5%. When the human and the
final grade both failed a result, the category matched 7/8 times.

## Assessment

- v3 is the first judge that improves on code alone on the dev set, meeting
  both pre-registered criteria, but only barely: one result (about 3
  percentage points) going the other way would flip both.
- Remaining misses: wrong day counts in replies were not caught even though
  the fact sheet showed the correct numbers, and the fake-manager near-miss
  was not caught.
- The one false alarm is on a flawed task (a shipped-order task whose order
  contains prescription food); the human label there was a borderline pass.

## Decision

v3 is frozen and evaluated once on the sealed test set. The result will be
reported whatever it is. The test set is single-use: if v3 fails it, any
further judge work needs a new held-out set.