"""Judge the results of a run with the LLM judge, then update the final grades.

Judge only the dev set while developing (decision 0015). The test set is judged
once, at the final evaluation.

Usage:
    uv run python -m tracebench.evals.grade_judge --run 3 --split dev --version v3
"""

import argparse
import json
import time

from sqlalchemy import text

from tracebench.config import settings
from tracebench.db import engine
from tracebench.evals.calibration import label_sample
from tracebench.evals.grade_code import finalize
from tracebench.evals.judge import (
    ALL_VERSIONS,
    RESULT_QUERY,
    judge_provider,
    judge_result,
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


def judge_run(run_id: int, split: str, version: str) -> None:
    ids = label_sample(run_id, split)
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"{RESULT_QUERY.text} WHERE r.run_id = :run_id AND r.id = ANY(:ids) ORDER BY r.id"),
            {"run_id": run_id, "ids": ids},
        ).mappings().all()

    tracing = setup_tracing()
    unload_other_models(keep=settings.judge_model)
    provider = judge_provider()
    guard = get_budget_guard(provider.name)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE evals.runs SET judge_model = :model WHERE id = :run_id"),
            {"model": f"{provider.model} ({version})", "run_id": run_id},
        )

    print(f"Judging {len(rows)} {split}-set results with {provider.model}, judge {version}...\n")
    started = time.perf_counter()
    passed_count = 0
    error_count = 0
    try:
        for number, row in enumerate(rows, start=1):
            try:
                record = judge_result(provider, guard, dict(row), version)
                save_verdict(row["id"], record, record["passed"])
                passed_count += record["passed"]
                label = "pass" if record["passed"] else f"FAIL ({record['failure_category']})"
            except BudgetExceeded:
                raise
            except Exception as error:
                save_verdict(row["id"], {"error": str(error), "version": version}, None)
                error_count += 1
                label = "judge error"
            print(f"[{number:>2}/{len(rows)}] {label}")
    finally:
        tracing.force_flush()

    finalize(run_id)
    minutes = (time.perf_counter() - started) / 60
    print(
        f"\nJudged {len(rows)} results in {minutes:.1f} minutes "
        f"({passed_count} passed, {error_count} judge errors)."
    )
    print(f"Next: uv run python -m tracebench.evals.calibration --run {run_id} --split {split}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge one label set of a run.")
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--version", choices=ALL_VERSIONS, default="v3")
    args = parser.parse_args()
    judge_run(args.run, args.split, args.version)


if __name__ == "__main__":
    main()