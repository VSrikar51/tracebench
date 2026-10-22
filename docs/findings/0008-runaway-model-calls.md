# 0008. Model calls need a length limit and a time limit

- **Date:** 2026-10-14
- **Found during:** judging the dev set with judge v2 (`phi4-mini`)

## What happened

The batch judge stopped making progress at result 23 of 32 and never
finished. The judge model was still generating: it had fallen into a loop
inside its structured (JSON) output, and nothing stopped it. No maximum
output length and no request timeout were set.

## Fix

The Ollama adapter accepts two optional limits:

- `max_tokens` (Ollama's `num_predict`): the judge's output is capped at
  1,024 tokens. A normal verdict is about 150–300 tokens.
- `timeout`: the judge client stops waiting after 180 seconds.

A call that hits either limit fails, and the batch judge records it as a
judge error (`judge_passed` is NULL), then continues. Calibration skips
judge errors rather than counting them as disagreements. The agent's
provider is unchanged, so the baseline is unaffected.

## Result

On the re-run, one result out of 32 (3%) became a judge error instead of
freezing the run, and all 32 finished in 5.1 minutes.

## Lesson

Any call to a model needs a length limit and a time limit. Without them, one
bad generation can freeze a whole pipeline. The rate of judge errors is also
a quality signal for the judge.