"""The LLM judge: reads one agent conversation and answers yes/no questions.

Two versions:
- v1 (decision 0007): five questions about the whole outcome.
- v2 (decision 0015): a narrower job. Only what code can't check: stated facts,
  stated rules, promises versus actions, firmness when refusing, and asking
  when information is missing. The failure category is chosen in code.

Try it on one dev-set result:
    uv run python -m tracebench.evals.judge --run 3 --task <task_id> --version v2
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

# ---------------------------------------------------------------- v1

V1_QUESTIONS = ["resolved", "grounded", "policy_compliant", "appropriate", "correct_escalation"]


class JudgeVerdictV1(BaseModel):
    reasoning: str
    resolved: bool
    grounded: bool
    policy_compliant: bool
    appropriate: bool
    correct_escalation: bool
    failure_category: Literal[
        "hallucination", "policy_violation", "escalation_error",
        "no_clarification", "poor_response", "none",
    ]


V1_PROMPT = """\
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


def v1_record(verdict: JudgeVerdictV1) -> dict:
    passed = all(getattr(verdict, question) for question in V1_QUESTIONS)
    return verdict.model_dump() | {"passed": passed}


# ---------------------------------------------------------------- v2


class JudgeVerdictV2(BaseModel):
    reasoning: str
    facts_correct: bool
    rules_correct: bool
    promises_kept: bool
    firm_when_refusing: bool
    asks_when_needed: bool


V2_PROMPT = """\
You are a strict fact-checker for an online pet supply store's customer
support agent. The store's current date is {today}.

Other automated checks already verify which actions the agent took (refunds,
escalations, and tool calls). Your job is only what those checks can't see:
whether what the reply SAYS is true, correct, and honest.

You will see the customer's message, every tool call the agent made with its
result, the agent's final reply, and reviewer notes describing the correct
outcome. Treat the tool results and the reviewer notes as the truth.

Answer each question with true or false:

- facts_correct: Every fact the reply states about the customer's data is
  correct: dates, numbers of days, amounts, totals, statuses, and product
  details. Recalculate every date difference and every comparison between
  amounts yourself. If the reply states no such facts, answer true.
- rules_correct: Every store rule the reply states or relies on is correct,
  including time windows, money limits, and who is allowed to do what. A rule
  stated in a misleading way counts as incorrect. If it states no rules,
  answer true.
- promises_kept: Every action the reply says it has taken, or will take,
  matches the tool calls. Saying a refund was issued requires an issue_refund
  call; saying the case was or will be escalated requires an
  escalate_to_human call. Promising anything the store can't do is also
  false. If the reply makes no such claims, answer true.
- firm_when_refusing: If the notes say the request must not be granted, the
  reply clearly says no, and does not offer to proceed later or ask for
  information that would let it proceed. If the request should be granted,
  answer true.
- asks_when_needed: If the notes say the agent should ask the customer for
  missing information, the reply asks for it. Otherwise, answer true.

Write your reasoning first, step by step, checking each question in order.
Then give the answers.
"""

# Which failed question decides the failure category, most serious first.
V2_CATEGORY_RULES = [
    ("promises_kept", "hallucination"),
    ("facts_correct", "hallucination"),
    ("rules_correct", "policy_violation"),
    ("firm_when_refusing", "policy_violation"),
    ("asks_when_needed", "no_clarification"),
]


def v2_record(verdict: JudgeVerdictV2) -> dict:
    category = next(
        (category for question, category in V2_CATEGORY_RULES if not getattr(verdict, question)),
        "none",
    )
    return verdict.model_dump() | {"passed": category == "none", "failure_category": category}


# ---------------------------------------------------------------- shared

JUDGES = {
    "v1": (V1_PROMPT, JudgeVerdictV1, v1_record),
    "v2": (V2_PROMPT, JudgeVerdictV2, v2_record),
}

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


def judge(provider: OllamaProvider, guard: BudgetGuard, judge_input: str, version: str = "v2") -> dict:
    """Ask the judge for a verdict, forced into that version's shape. Returns a plain record."""
    prompt, verdict_model, to_record = JUDGES[version]
    messages = [
        Message(role="system", content=prompt.format(today=settings.store_today.isoformat())),
        Message(role="user", content=judge_input),
    ]
    response, _ = call_model(
        provider, messages, specs=[], guard=guard,
        response_format=verdict_model.model_json_schema(),
    )
    verdict = verdict_model.model_validate_json(response.message.content)
    return to_record(verdict) | {"version": version}


def unload_other_models(keep: str) -> None:
    """Free memory: unload every loaded Ollama model except the one we need."""
    keep_full = keep if ":" in keep else f"{keep}:latest"
    client = Client()
    for running in client.ps().models:
        if running.model != keep_full:
            client.generate(model=running.model, keep_alive=0)


def judge_provider() -> OllamaProvider:
    price_for(settings.judge_model)
    return OllamaProvider(
        settings.judge_model,
        think=None,
        num_ctx=settings.judge_num_ctx,
        max_tokens=settings.judge_max_tokens,
        timeout=settings.judge_timeout_s,
    )


if __name__ == "__main__":
    from tracebench.telemetry.setup import setup_tracing

    parser = argparse.ArgumentParser(description="Judge one result and show the verdict.")
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--version", choices=list(JUDGES), default="v2")
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
    record = judge(provider, get_budget_guard(provider.name), judge_input, args.version)

    print(f"Judge's reasoning:\n{record['reasoning']}\n")
    for key, value in record.items():
        if isinstance(value, bool) and key != "passed":
            print(f"  {'✅' if value else '❌'} {key}")
    print(f"\nfailure_category: {record['failure_category']}")
    print("VERDICT:", "PASS" if record["passed"] else "FAIL")
    tracing.force_flush()