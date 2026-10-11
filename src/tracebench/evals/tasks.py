"""Load eval tasks from YAML files, check them, and fingerprint the dataset."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from tracebench.agent.registry import TOOLS_BY_NAME
from tracebench.store.policy_search import read_policies

TASKS_DIR = Path(__file__).resolve().parents[3] / "evals" / "tasks"

Category = Literal[
    "order_status",
    "refund_allowed",
    "refund_denied",
    "policy_question",
    "inventory",
    "escalation",
    "ambiguous",
    "adversarial",
]


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refund_usd: float = 0.0
    escalated: bool = False
    tools_required: list[str] = []
    tools_forbidden: list[str] = []
    cite_policies: list[str] = []
    asks_clarification: bool = False


class EvalTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    message: str
    smoke: bool = False
    expected: Expected
    notes: str = ""


def dataset_version(files: list[Path]) -> str:
    """A fingerprint of every task file. Change any file, and the fingerprint changes."""
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(TASKS_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def check_task(task: EvalTask, policy_ids: set[str]) -> list[str]:
    """Find mistakes in a task that the format alone can't catch."""
    problems = []
    for tool in task.expected.tools_required + task.expected.tools_forbidden:
        if tool not in TOOLS_BY_NAME:
            problems.append(f"{task.id}: unknown tool '{tool}'")
    for policy in task.expected.cite_policies:
        if policy not in policy_ids:
            problems.append(f"{task.id}: unknown policy '{policy}'")
    overlap = set(task.expected.tools_required) & set(task.expected.tools_forbidden)
    if overlap:
        problems.append(f"{task.id}: tools both required and forbidden: {sorted(overlap)}")
    return problems


def load_tasks(smoke_only: bool = False) -> tuple[list[EvalTask], str]:
    """Load and check every task. Returns the tasks and the dataset version."""
    files = sorted(TASKS_DIR.rglob("*.yaml"))
    policy_ids = {policy["id"] for policy in read_policies()}

    tasks: list[EvalTask] = []
    problems: list[str] = []
    for path in files:
        for raw in yaml.safe_load(path.read_text()) or []:
            task = EvalTask.model_validate(raw)
            problems.extend(check_task(task, policy_ids))
            tasks.append(task)

    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            problems.append(f"Duplicate task id: {task.id}")
        seen.add(task.id)

    if problems:
        raise ValueError("Problems in eval tasks:\n" + "\n".join(problems))

    version = dataset_version(files)
    if smoke_only:
        tasks = [task for task in tasks if task.smoke]
    return tasks, version


if __name__ == "__main__":
    from collections import Counter

    tasks, version = load_tasks()
    print(f"Dataset version: {version}")
    print(f"Tasks: {len(tasks)} ({sum(task.smoke for task in tasks)} in the smoke subset)")
    for category, count in sorted(Counter(task.category for task in tasks).items()):
        print(f"  {category}: {count}")