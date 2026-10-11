# 0012. Eval tasks live as YAML files in the repo

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The eval harness needs about 60 tasks, each with a customer message, expected
tool calls, an expected end state, and policies to cite. Scores are only
comparable if they come from the same version of the task set.

## Options considered

1. Tasks stored in the database only
2. Tasks stored as YAML files in the repo, loaded into the database per run
3. Tasks stored as files only, with no database copy

## Decision

Option 2. Tasks live in `evals/tasks/`:

- `evals/tasks/handwritten/`: written by hand (adversarial, ambiguous,
  escalation)
- `evals/tasks/generated/`: written by the task generator script, committed
  so they can be reviewed, and never edited by hand

Every eval run records a dataset version: a hash of all task files.

## Why

- Tasks are visible and reviewable on GitHub, and every change is in git
  history.
- The dataset version makes it impossible to accidentally compare scores
  from different task sets, which keeps before/after claims honest.
- A database copy lets results and dashboards join tasks directly.

## Consequences

- Task files are validated on load: unknown fields, unknown tool names, and
  unknown policy IDs are errors.
- Changing any task changes the dataset version, so older scores are not
  compared against newer ones.