"""Human labels and judge calibration.

The labeling sample is about half of each task category in a run, picked at
random with a fixed seed, so it's fair (not hand-picked) and repeatable.

Calibration compares each grader (code checks, the judge, and the final
grade) with the human labels.

Usage:
    uv run python -m tracebench.evals.calibration --run 3 --labeler srikar
"""

import argparse
import math
import random
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text

from tracebench.db import engine

SAMPLE_SEED = 7
SAMPLE_FRACTION = 0.5


def label_sample(run_id: int, split: str = "dev") -> list[int]:
    """Result IDs for one label set.

    dev: about half of each task category, chosen with a fixed seed.
    test: every other result in the run, which come from different tasks.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id, t.category
            FROM evals.results AS r
            JOIN evals.tasks AS t
              ON t.id = r.task_id AND t.dataset_version = r.dataset_version
            WHERE r.run_id = :run_id
            ORDER BY r.id
        """), {"run_id": run_id}).mappings().all()

    by_category: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row["id"])

    rng = random.Random(SAMPLE_SEED)
    dev = []
    for category in sorted(by_category):
        ids = by_category[category]
        dev.extend(rng.sample(ids, math.ceil(len(ids) * SAMPLE_FRACTION)))

    if split == "dev":
        return sorted(dev)
    if split == "test":
        return sorted(set(row["id"] for row in rows) - set(dev))
    raise ValueError(f"Unknown split '{split}'. Use 'dev' or 'test'.")


@dataclass
class Agreement:
    """How one grader's pass/fail compares with the human's."""

    both_pass: int = 0
    both_fail: int = 0
    false_alarm: int = 0  # the human passed it, the grader failed it
    missed: int = 0  # the human failed it, the grader passed it

    def add(self, human_passed: bool, grader_passed: bool) -> None:
        if human_passed and grader_passed:
            self.both_pass += 1
        elif not human_passed and not grader_passed:
            self.both_fail += 1
        elif human_passed:
            self.false_alarm += 1
        else:
            self.missed += 1

    @property
    def total(self) -> int:
        return self.both_pass + self.both_fail + self.false_alarm + self.missed

    @property
    def agreement(self) -> float:
        return (self.both_pass + self.both_fail) / self.total

    @property
    def kappa(self) -> float | None:
        """Cohen's kappa: agreement beyond what chance alone would give."""
        human_pass = (self.both_pass + self.false_alarm) / self.total
        grader_pass = (self.both_pass + self.missed) / self.total
        chance = human_pass * grader_pass + (1 - human_pass) * (1 - grader_pass)
        if chance == 1:
            return None
        return (self.agreement - chance) / (1 - chance)

    @property
    def catch_rate(self) -> float | None:
        """Of the results the human failed, how many the grader also failed."""
        human_fails = self.both_fail + self.missed
        return self.both_fail / human_fails if human_fails else None

    @property
    def false_alarm_rate(self) -> float | None:
        """Of the results the human passed, how many the grader failed anyway."""
        human_passes = self.both_pass + self.false_alarm
        return self.false_alarm / human_passes if human_passes else None


def kappa_meaning(kappa: float | None) -> str:
    if kappa is None:
        return "undefined"
    if kappa < 0:
        return "worse than chance"
    for limit, meaning in [(0.2, "slight"), (0.4, "fair"), (0.6, "moderate"), (0.8, "substantial")]:
        if kappa <= limit:
            return meaning
    return "almost perfect"


def fmt(value: float | None, percent: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}" if percent else f"{value:.2f}"


def calibrate(run_id: int, labeler: str, split: str = "dev") -> None:
    ids = label_sample(run_id, split)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.task_id,
                   h.passed AS human_passed,
                   h.failure_category AS human_category,
                   h.notes,
                   r.code_passed,
                   r.judge_passed,
                   r.passed AS final_passed,
                   r.failure_category AS final_category,
                   r.judge_verdict->>'failure_category' AS judge_category
            FROM evals.human_labels AS h
            JOIN evals.results AS r ON r.id = h.result_id
            JOIN evals.tasks AS t
              ON t.id = r.task_id AND t.dataset_version = r.dataset_version
            WHERE r.run_id = :run_id AND h.labeler = :labeler AND r.id = ANY(:ids)
            ORDER BY t.category, r.task_id
        """), {"run_id": run_id, "labeler": labeler, "ids": ids}).mappings().all()

    if not rows:
        print(f"No labels from '{labeler}' for run {run_id}.")
        return

    graders = {
        "Code checks": "code_passed",
        "Judge": "judge_passed",
        "Final (code + judge)": "final_passed",
    }
    results = {}
    for name, column in graders.items():
        agreement = Agreement()
        for row in rows:
            if row[column] is not None:
                agreement.add(row["human_passed"], row[column])
        results[name] = agreement

    human_passes = sum(row["human_passed"] for row in rows)
    print(f"Calibration · run {run_id} · {split} set · labeler {labeler} · {len(rows)} labels")
    print(f"Human pass rate: {human_passes}/{len(rows)} ({human_passes / len(rows):.0%})\n")

    print(f"{'Grader':<22} {'Agree':>6} {'Kappa':>6}  {'Meaning':<18} {'Catch':>6} {'False alarm':>12}")
    for name, a in results.items():
        if a.total == 0:
            print(f"{name:<22} (no data)")
            continue
        print(
            f"{name:<22} {fmt(a.agreement):>6} {fmt(a.kappa, percent=False):>6}  "
            f"{kappa_meaning(a.kappa):<18} {fmt(a.catch_rate):>6} {fmt(a.false_alarm_rate):>12}"
        )

    both_failed = [row for row in rows if not row["human_passed"] and not row["final_passed"]]
    if both_failed:
        same = sum(row["human_category"] == row["final_category"] for row in both_failed)
        print(
            f"\nWhen both you and the final grade failed a result, the failure category "
            f"matched {same}/{len(both_failed)} times."
        )

    disagreements = [
        row for row in rows
        if row["judge_passed"] is not None and row["judge_passed"] != row["human_passed"]
    ]
    print(f"\nJudge disagreements ({len(disagreements)}):")
    for row in disagreements:
        you = "pass" if row["human_passed"] else f"fail ({row['human_category']})"
        judge = "pass" if row["judge_passed"] else f"fail ({row['judge_category']})"
        print(f"\n  {row['task_id']}")
        print(f"    you: {you}   judge: {judge}")
        if row["notes"]:
            print(f"    your notes: {row['notes']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare the graders with human labels.")
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--labeler", default="srikar")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    calibrate(args.run, args.labeler, args.split)


if __name__ == "__main__":
    main()