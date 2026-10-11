# 0002. Baseline: keyword search misses synonyms

- **Date:** 2026-10-10
- **Search:** Postgres full-text search, OR-matched and ranked with `ts_rank`
  (see decision 0009)

## Results

| Query | Top results (score) | Verdict |
|---|---|---|
| "My dog bed arrived damaged, can I get a refund?" | `damaged-items` (0.257), `returns` (0.132), `refunds` (0.124) | Correct |
| "Can I return opened cat food?" | `returns` (0.325), `prescription-food` (0.228), `loyalty` (0.122) | Correct first result, two noisy ones |
| "My cat toy came broken" | `returns` (0.061) | **Miss:** `damaged-items` not found |

## What went wrong

- "Broken" never appears in the `damaged-items` policy, so keyword search
  can't connect them. `returns` matched only on the word "toy".
- In the second query, `prescription-food` and `loyalty` matched on single
  shared words ("food", "return") without being relevant.

## What this motivates

- Measuring retrieval with recall@3 across all eval tasks
- The planned upgrade to hybrid (keyword + embedding) search, judged by how
  much it improves recall@3