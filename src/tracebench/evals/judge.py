"""The LLM judge: reads one agent conversation and answers five yes/no questions.

Decision 0007: a yes/no checklist, with reasoning written before the verdict.
The judge is a different model family from the agent, to avoid self-preference
bias (decision 0003).

Try it on one result:
    uv run python -m tracebench.evals.judge --run 1 --task gen-refund_denied-001
"""

import argparse
import json
from typing import Literal

from ollama import Client
from pydantic import BaseModel
from sqlalchemy import text

from tracebench.agent.loop import call_model
from tracebench.config import settings
from tracebench.db import engine
from tracebench.llm.ollama_provider import OllamaProvider
from tracebench.llm.types import Message
from tracebench.telemetry.cost import BudgetGuard, get_budget_guard, price_for

QUESTIONS = ["resolved", "grounded", "policy_compliant", "appropriate", "correct_escalation"]

JudgeCategory = Literal[
    "hallucination",
    "policy_violation",
    "escalation_error",
    "no_clarification",
    "poor_response",
    "none",
]


class JudgeVerdict(BaseModel):
    reasoning: str
    resolved: bool
    grounded: bool
    policy_compliant: bool
    appropriate: bool
    correct_escalation: bool
    failure_category: JudgeCategory

    @property
    def passed(self) -> bool:
        return all(getattr(self, question) for question in QUESTIONS)


JUDGE_PROMPT = """\
You are a strict quality reviewer for an online pet supply store's customer
support agent. The store's current date is {today}.

You will see the customer's message, every tool call the agent made with its
result, the agent's final reply, and reviewer notes describing the correct
outcome. Treat the tool results and the reviewer notes as the truth.

Answer each question with true or false:

- resolved: Did the reply correctly handle what the customer asked? If the
  notes say the agent should ask for missing information, this is true only
  if it asked instead of acting or guessing.
- grounded: Is every fact in the reply (dates, deadlines, amounts, statuses,
  policy rules) supported by the tool results or the notes? Check any date
  arithmetic yourself. One wrong or invented fact makes this false.
- policy_compliant: Does the reply follow the store's policies, as shown in
  the tool results and the notes?
- appropriate: Is the reply professional and clear, with no promises the
  agent can't keep?
- correct_escalation: Did the agent escalate to a human exactly when the
  notes say it should, and not otherwise?

First write your reasoning, step by step. Then give the answers. If any answer
is false, set failure_category to the single best fit:

- hallucination: invented or wrong facts
- policy_violation: broke or misstated a policy
- escalation_error: escalated when it shouldn't have, or didn't when it should
- no_clarification: acted or guessed when it should have asked
- poor_response: incomplete, confusing, or unprofessional

If every answer is true, set failure_category to "none".
"""

RESULT_LIMIT = 1500


def load_tool_calls(trace_id: str) -> list[dict]:
    """The agent's tool calls for one run, in order, read from the trace."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tc.tool_name, tc.arguments, tc.result
            FROM telemetry.tool_calls AS tc
            JOIN telemetry.spans AS s USING (span_id)
            WHERE tc.trace_id = :trace_id
            ORDER BY s.start_time
        """), {"trace_id": trace_id}).mappings().all()
    return [dict(row) for row in rows]


def describe_expected(expected: dict) -> str:
    """Turn the answer key into a short sentence for the judge."""
    parts = [
        f"refund ${expected['refund_usd']:.2f}" if expected["refund_usd"] else "no refund",
        "escalate to a human" if expected["escalated"] else "no escalation",
    ]
    if expected.get("asks_clarification"):
        parts.append("ask the customer for the missing information")
    return ", ".join(parts)


def build_judge_input(
    message: str, expected: dict, notes: str, tool_calls: list[dict], reply: str
) -> str:
    """Everything the judge needs to see, as one readable document."""
    lines = ["## Customer message", message, "", "## Agent's tool calls"]
    if not tool_calls:
        lines.append("(none)")
    for number, call in enumerate(tool_calls, start=1):
        result = json.dumps(call["result"], ensure_ascii=False)
        if len(result) > RESULT_LIMIT:
            result = result[:RESULT_LIMIT] + "…"
        lines.append(f"{number}. {call['tool_name']}({json.dumps(call['arguments'], ensure_ascii=False)})")
        lines.append(f"   result: {result}")
    lines += [
        "",
        "## Agent's final reply",
        reply,
        "",
        "## Reviewer notes (the correct outcome)",
        f"Expected outcome: {describe_expected(expected)}.",
        notes,
    ]
    return "\n".join(lines)


def judge(provider: OllamaProvider, guard: BudgetGuard, judge_input: str) -> JudgeVerdict:
    """Ask the judge model for a verdict, forced into the JudgeVerdict shape."""
    messages = [
        Message(role="system", content=JUDGE_PROMPT.format(today=settings.store_today.isoformat())),
        Message(role="user", content=judge_input),
    ]
    response, _ = call_model(
        provider, messages, specs=[], guard=guard,
        response_format=JudgeVerdict.model_json_schema(),
    )
    return JudgeVerdict.model_validate_json(response.message.content)


def unload_other_models(keep: str) -> None:
    """Free memory: unload every loaded Ollama model except the one we need."""
    keep_full = keep if ":" in keep else f"{keep}:latest"
    client = Client()
    for running in client.ps().models:
        if running.model != keep_full:
            client.generate(model=running.model, keep_alive=0)


def judge_provider() -> OllamaProvider:
    price_for(settings.judge_model)
    return OllamaProvider(settings.judge_model, think=None, num_ctx=settings.judge_num_ctx)


if __name__ == "__main__":
    from tracebench.telemetry.setup import setup_tracing

    parser = argparse.ArgumentParser(description="Judge one result and show the verdict.")
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT r.reply, r.trace_id, t.message, t.expected, t.notes
            FROM evals.results AS r
            JOIN evals.tasks AS t
              ON t.id = r.task_id AND t.dataset_version = r.dataset_version
            WHERE r.run_id = :run_id AND r.task_id = :task_id
        """), {"run_id": args.run, "task_id": args.task}).mappings().first()
    if row is None:
        parser.error(f"No result for task {args.task} in run {args.run}.")

    judge_input = build_judge_input(
        row["message"], row["expected"], row["notes"], load_tool_calls(row["trace_id"]), row["reply"]
    )
    print(judge_input)
    print("\n" + "=" * 70 + "\n")

    tracing = setup_tracing()
    unload_other_models(keep=settings.judge_model)
    provider = judge_provider()
    verdict = judge(provider, get_budget_guard(provider.name), judge_input)

    print(f"Judge's reasoning:\n{verdict.reasoning}\n")
    for question in QUESTIONS:
        print(f"  {'✅' if getattr(verdict, question) else '❌'} {question}")
    print(f"\nfailure_category: {verdict.failure_category}")
    print("VERDICT:", "PASS" if verdict.passed else "FAIL")
    tracing.force_flush()