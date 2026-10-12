"""Judge every result in a run with the LLM judge, then update the final grades.

Usage:
    uv run python -m tracebench.evals.grade_judge --run 3
"""

import argparse
import json
import time

from sqlalchemy import text

from tracebench.config import settings
from tracebench.db import engine
from tracebench.evals.grade_code import finalize, print_report
from tracebench.evals.judge import (
    build_judge_input,
    judge,
    judge_provider,
    load_tool_calls,
    unload_other_models,
)
from tracebench.telemetry.cost import BudgetExceeded, get_budget_guard
from tracebench.telemetry.setup import setup_tracing


def save_verdict(result_id: int, verdict: dict, passed: bool | None) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE evals.results
            SET judge_verdict = CAST(:verdict AS JSONB), judge_passed = :passed
            WHERE id = :id
        """), {"verdict": json.dumps(verdict), "passed": passed, "id": result_id})


def judge_run(run_id: int) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id, r.task_id, r.reply, r.trace_id, t.message, t.expected, t.notes
            FROM evals.results AS r
            JOIN evals.tasks AS t
              ON t.id = r.task_id AND t.dataset_version = r.dataset_version
            WHERE r.run_id = :run_id
            ORDER BY r.id
        """), {"run_id": run_id}).mappings().all()

    tracing = setup_tracing()
    unload_other_models(keep=settings.judge_model)
    provider = judge_provider()
    guard = get_budget_guard(provider.name)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE evals.runs SET judge_model = :model WHERE id = :run_id"),
            {"model": provider.model, "run_id": run_id},
        )

    print(f"Judging {len(rows)} results with {provider.model}...\n")
    started = time.perf_counter()
    try:
        for number, row in enumerate(rows, start=1):
            judge_input = build_judge_input(
                row["message"], row["expected"], row["notes"],
                load_tool_calls(row["trace_id"]), row["reply"],
            )
            try:
                verdict = judge(provider, guard, judge_input)
                save_verdict(row["id"], verdict.model_dump() | {"passed": verdict.passed}, verdict.passed)
                label = "pass" if verdict.passed else f"FAIL ({verdict.failure_category})"
            except BudgetExceeded:
                raise
            except Exception as error:
                save_verdict(row["id"], {"error": str(error)}, None)
                label = "judge error"
            print(f"[{number:>2}/{len(rows)}] {row['task_id']:<45} {label}")
    finally:
        tracing.force_flush()

    finalize(run_id)
    minutes = (time.perf_counter() - started) / 60
    print(f"\nJudged in {minutes:.1f} minutes.\n")
    print_report(run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge every result in a run.")
    parser.add_argument("--run", type=int, required=True, help="The run ID to judge.")
    args = parser.parse_args()
    judge_run(args.run)


if __name__ == "__main__":
    main()