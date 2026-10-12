# 0006. Dates depended on the database's display time zone

- **Date:** 2026-10-11
- **Found by:** reading a judge test; order 1007 showed `ordered_on`
  2026-10-02, a day after the store date (2026-10-01)

## Cause

Timestamps are stored correctly as `TIMESTAMPTZ` (in UTC from the seed
script), but Postgres converts them to the session's time zone when they are
read. The database default was UTC+8, so evening UTC times read back as the
next calendar day. `get_order`'s `day()` helper and the task generator both
took `.date()` of those values.

## Impact

- Dates shown to the agent could be one day later than intended.
- The task generator's "days since delivery" and window decisions used the
  same shifted dates, so answers near a window boundary could be wrong.
- Results depended on how Postgres was installed, not on the code.

## Fix

The app's database engine sets `timezone=UTC` on every connection, so the
store's dates are always UTC. Tasks were regenerated, producing a new dataset
version; the baseline must be re-run on it.

## Lesson

A frozen clock needs an agreed time zone. Any date logic should state which
zone it uses instead of inheriting one from the environment.