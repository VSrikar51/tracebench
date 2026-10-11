"""Run eval tasks through the agent and save every result.

Usage:
    uv run python -m tracebench.evals.runner --label baseline --smoke
"""

import argparse
import json
import subprocess
import time

from sqlalchemy import text

from tracebench.agent.loop import MAX_STEPS, AgentResult, run_agent
from tracebench.config import settings
from tracebench.db import engine
from tracebench.evals.tasks import EvalTask, load_tasks
from tracebench.llm.ollama_provider import OllamaProvider
from tracebench.llm.types import LLMProvider, Message
from tracebench.store.seed import seed
from tracebench.telemetry.setup import setup_tracing


def git_commit() -> str | None:
    """The current code version, marked '-dirty' if there are uncommitted changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        changes = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}-dirty" if changes else commit


def save_tasks(tasks: list[EvalTask], version: str) -> None:
    """Copy the tasks into the database, once per dataset version."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO evals.tasks (dataset_version, id, category, message, smoke, expected, notes)
            VALUES (:version, :id, :category, :message, :smoke, CAST(:expected AS JSONB), :notes)
            ON CONFLICT (dataset_version, id) DO NOTHING
        """), [
            {
                "version": version,
                "id": task.id,
                "category": task.category,
                "message": task.message,
                "smoke": task.smoke,
                "expected": json.dumps(task.expected.model_dump()),
                "notes": task.notes,
            }
            for task in tasks
        ])


def start_run(label: str, version: str, smoke_only: bool, provider: LLMProvider) -> int:
    config = {
        "agent_think": settings.agent_think,
        "agent_num_ctx": settings.agent_num_ctx,
        "max_steps": MAX_STEPS,
        "trace_content": settings.trace_content,
        "store_today": settings.store_today.isoformat(),
    }
    with engine.begin() as conn:
        return conn.execute(text("""
            INSERT INTO evals.runs
                (label, dataset_version, smoke_only, agent_provider, agent_model, git_commit, config)
            VALUES
                (:label, :version, :smoke_only, :provider, :model, :commit, CAST(:config AS JSONB))
            RETURNING id
        """), {
            "label": label,
            "version": version,
            "smoke_only": smoke_only,
            "provider": provider.name,
            "model": provider.model,
            "commit": git_commit(),
            "config": json.dumps(config),
        }).scalar_one()


def finish_run(run_id: int, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE evals.runs SET status = :status, finished_at = now() WHERE id = :run_id
        """), {"status": status, "run_id": run_id})


def observe(result: AgentResult) -> dict:
    """Record what the agent did, before the store is reset for the next task."""
    with engine.connect() as conn:
        refunded_cents = conn.execute(text(
            "SELECT COALESCE(sum(amount_cents), 0) FROM store.refunds"
        )).scalar_one()
        escalations = conn.execute(text("SELECT count(*) FROM store.escalations")).scalar_one()

    tools_called = []
    tool_errors = []
    for message in result.messages:
        if message.role == "assistant":
            tools_called.extend(call.name for call in message.tool_calls)
        elif message.role == "tool" and "error" in json.loads(message.content):
            tool_errors.append(message.tool_name)

    return {
        "refunded_usd": refunded_cents / 100,
        "escalations": escalations,
        "tools_called": tools_called,
        "tool_errors": tool_errors,
    }


def save_result(
    run_id: int, version: str, task: EvalTask, result: AgentResult,
    observed: dict, duration_ms: float,
) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO evals.results
                (run_id, dataset_version, task_id, trace_id, reply, stop_reason, steps,
                 input_tokens, output_tokens, cost_usd, duration_ms, observed)
            VALUES
                (:run_id, :version, :task_id, :trace_id, :reply, :stop_reason, :steps,
                 :input_tokens, :output_tokens, :cost_usd, :duration_ms, CAST(:observed AS JSONB))
        """), {
            "run_id": run_id,
            "version": version,
            "task_id": task.id,
            "trace_id": result.trace_id,
            "reply": result.reply,
            "stop_reason": result.stop_reason,
            "steps": result.steps,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "duration_ms": duration_ms,
            "observed": json.dumps(observed),
        })


def warm_up(provider: LLMProvider) -> None:
    """One throwaway call, so the first task isn't slowed down by loading the model."""
    print("Warming up the model...")
    provider.chat([Message(role="user", content="Reply with the word OK.")])


def run_eval(label: str, smoke_only: bool) -> int:
    tasks, version = load_tasks(smoke_only=smoke_only)
    tracing = setup_tracing()
    provider = OllamaProvider(settings.agent_model, settings.agent_think, settings.agent_num_ctx)

    save_tasks(tasks, version)
    run_id = start_run(label, version, smoke_only, provider)
    print(f"Run {run_id} '{label}': {len(tasks)} tasks, dataset {version}, model {provider.model}\n")

    warm_up(provider)
    status = "failed"
    run_started = time.perf_counter()
    try:
        for number, task in enumerate(tasks, start=1):
            seed(verbose=False)
            started = time.perf_counter()
            result = run_agent(provider, task.message)
            duration_ms = (time.perf_counter() - started) * 1000

            observed = observe(result)
            save_result(run_id, version, task, result, observed, duration_ms)
            print(
                f"[{number:>2}/{len(tasks)}] {task.id:<45} "
                f"{result.stop_reason:<10} {result.steps} steps  {duration_ms / 1000:5.1f}s"
            )
        status = "completed"
    finally:
        finish_run(run_id, status)
        seed(verbose=False)
        tracing.force_flush()

    minutes = (time.perf_counter() - run_started) / 60
    print(f"\nRun {run_id} {status} in {minutes:.1f} minutes.")
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval tasks through the agent.")
    parser.add_argument("--label", required=True, help="A name for this run, e.g. 'baseline'.")
    parser.add_argument("--smoke", action="store_true", help="Only run the smoke subset.")
    args = parser.parse_args()
    run_eval(args.label, args.smoke)


if __name__ == "__main__":
    main()