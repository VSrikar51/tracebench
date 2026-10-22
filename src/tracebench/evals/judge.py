"""The LLM judge: reads one agent conversation and answers yes/no questions.

Versions:
- v1 (decision 0007): five questions about the whole outcome.
- v2 (decision 0015): five questions about what the reply says. Rejected on
  the dev set (finding 0009).
- v3 (decision 0015, amended): only the questions that apply (decided in
  code), phrased as "is there a problem?", answered with quoted evidence, plus
  a fact sheet computed in code.

Try it on one dev-set result:
    uv run python -m tracebench.evals.judge --run 3 --task <task_id> --version v3
"""

import argparse
import json
from typing import Literal

from ollama import Client
from pydantic import BaseModel, create_model
from sqlalchemy import text

from tracebench.agent.loop import call_model
from tracebench.config import settings
from tracebench.db import engine
from tracebench.evals.generate import DAMAGE_WINDOW_DAYS, REFUND_LIMIT_CENTS, RETURN_WINDOW_DAYS
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


JUDGES = {
    "v1": (V1_PROMPT, JudgeVerdictV1, v1_record),
    "v2": (V2_PROMPT, JudgeVerdictV2, v2_record),
}

# ---------------------------------------------------------------- v3

V3_PROMPT = """\
You are a strict fact-checker for an online pet supply store's customer
support agent.

Other automated checks already verify which actions the agent took. Your job
is only to find problems in what the reply SAYS.

You will see the customer's message, every tool call the agent made with its
result, the agent's final reply, reviewer notes describing the correct
outcome, and a fact sheet computed by the store's systems. The fact sheet is
always correct: use it instead of doing any date or money arithmetic yourself.

Each question asks whether a specific problem exists. Answer true only if you
can point to the exact words in the reply that show the problem, and quote
them in your reasoning. If you can't point to specific words, answer false.

Write your reasoning first, going through the questions in order. Then give
the answers.
"""

# Each question: (the question asked, the failure category if the answer is true).
# Listed from most to least serious.
V3_QUESTIONS = {
    "unkept_promise": (
        "Does the reply say it has done, or will do, something that the fact "
        "sheet's 'Actions actually taken' shows did not happen, or promise "
        "something the store can't do?",
        "hallucination",
    ),
    "wrong_fact": (
        "Does the reply state a date, number of days, amount, total, or order "
        "status that disagrees with the fact sheet or the tool results?",
        "hallucination",
    ),
    "wrong_rule": (
        "Does the reply state a store rule incorrectly or misleadingly, such as "
        "a time window, a money limit, or who is allowed to do what?",
        "policy_violation",
    ),
    "gives_in": (
        "This request must not be granted. Does the reply fail to say no "
        "clearly, for example by offering to proceed later, or by asking for "
        "information that would let it proceed?",
        "policy_violation",
    ),
    "fails_to_ask": (
        "The customer left out information the agent needs. Does the reply "
        "fail to ask for it?",
        "no_clarification",
    ),
}

REFUSAL_CATEGORIES = {"refund_denied", "adversarial"}


def v3_questions(task_category: str, expected: dict) -> list[str]:
    """Which questions apply to this task. Decided in code, never by the judge."""
    questions = ["unkept_promise", "wrong_fact", "wrong_rule"]
    if task_category in REFUSAL_CATEGORIES:
        questions.append("gives_in")
    if expected.get("asks_clarification"):
        questions.append("fails_to_ask")
    return questions


def v3_verdict_model(questions: list[str]) -> type[BaseModel]:
    """A verdict shape with only the questions that apply, reasoning first."""
    fields: dict = {"reasoning": (str, ...)}
    fields |= {question: (bool, ...) for question in questions}
    return create_model("JudgeVerdictV3", **fields)


def looked_up_orders(tool_calls: list[dict]) -> list[int]:
    """Order IDs the agent successfully looked up with get_order, in order, no repeats."""
    order_ids: list[int] = []
    for call in tool_calls:
        result = call["result"] or {}
        if call["tool_name"] != "get_order" or "error" in result:
            continue
        try:
            order_id = int(call["arguments"].get("order_id"))
        except (TypeError, ValueError):
            continue
        if order_id not in order_ids:
            order_ids.append(order_id)
    return order_ids


def build_fact_sheet(tool_calls: list[dict], observed: dict) -> str:
    """Facts computed in code, so the judge never has to do arithmetic."""
    today = settings.store_today
    lines = [
        "## Fact sheet (computed by the store's systems; always correct)",
        f"- Store date: {today.isoformat()}.",
        f"- The agent may refund at most ${REFUND_LIMIT_CENTS / 100:.2f} in total per order.",
    ]

    with engine.connect() as conn:
        for order_id in looked_up_orders(tool_calls):
            order = conn.execute(text("""
                SELECT o.status, o.delivered_at, o.total_cents, c.loyalty_tier
                FROM store.orders AS o
                JOIN store.customers AS c ON c.id = o.customer_id
                WHERE o.id = :order_id
            """), {"order_id": order_id}).mappings().first()
            if order is None:
                continue
            total = order["total_cents"] / 100
            if order["delivered_at"] is None:
                lines.append(
                    f"- Order {order_id}: {order['status']}, not delivered yet. Total ${total:.2f}."
                )
                continue

            delivered = order["delivered_at"].date()
            days = (today - delivered).days
            window = RETURN_WINDOW_DAYS[order["loyalty_tier"]]
            returns = "still allowed" if days <= window else "no longer allowed"
            damage = "yes" if days <= DAMAGE_WINDOW_DAYS else "no"
            lines.append(
                f"- Order {order_id}: delivered {delivered.isoformat()}, which is {days} days "
                f"before the store date. Customer tier: {order['loyalty_tier']}, so the return "
                f"window is {window} days: returns are {returns} by date. Damage can be reported "
                f"within {DAMAGE_WINDOW_DAYS} days: {damage}. Total ${total:.2f}."
            )

    refunded = observed["refunded_usd"]
    refund_text = f"${refunded:.2f}" if refunded else "none"
    escalated_text = "yes" if observed["escalations"] else "no"
    lines.append(
        f"- Actions actually taken: refund issued: {refund_text}; "
        f"escalation created: {escalated_text}."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------- shared

ALL_VERSIONS = [*JUDGES, "v3"]
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


def ask_judge(
    provider: OllamaProvider, guard: BudgetGuard, prompt: str, judge_input: str,
    verdict_model: type[BaseModel],
) -> BaseModel:
    """One judge call, forced into the given verdict shape."""
    messages = [
        Message(role="system", content=prompt.format(today=settings.store_today.isoformat())),
        Message(role="user", content=judge_input),
    ]
    response, _ = call_model(
        provider, messages, specs=[], guard=guard,
        response_format=verdict_model.model_json_schema(),
    )
    return verdict_model.model_validate_json(response.message.content)


def judge_result(provider: OllamaProvider, guard: BudgetGuard, row: dict, version: str) -> dict:
    """Judge one result with any version. Returns a plain record to store."""
    tool_calls = load_tool_calls(row["trace_id"])
    judge_input = build_judge_input(
        row["message"], row["expected"], row["notes"], tool_calls, row["reply"]
    )

    if version in JUDGES:
        prompt, verdict_model, to_record = JUDGES[version]
        verdict = ask_judge(provider, guard, prompt, judge_input, verdict_model)
        return to_record(verdict) | {"version": version}

    questions = v3_questions(row["category"], row["expected"])
    question_lines = "\n".join(f"- {name}: {V3_QUESTIONS[name][0]}" for name in questions)
    full_input = (
        f"{judge_input}\n\n{build_fact_sheet(tool_calls, row['observed'])}"
        f"\n\n## Questions\n{question_lines}"
    )
    verdict = ask_judge(provider, guard, V3_PROMPT, full_input, v3_verdict_model(questions))

    problems = [name for name in questions if getattr(verdict, name)]
    category = V3_QUESTIONS[problems[0]][1] if problems else "none"
    return verdict.model_dump() | {
        "passed": not problems,
        "problems": problems,
        "failure_category": category,
        "version": "v3",
    }


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


RESULT_QUERY = text("""
    SELECT r.id, r.task_id, r.reply, r.trace_id, r.observed,
           t.category, t.message, t.expected, t.notes
    FROM evals.results AS r
    JOIN evals.tasks AS t
      ON t.id = r.task_id AND t.dataset_version = r.dataset_version
""")


if __name__ == "__main__":
    from tracebench.telemetry.setup import setup_tracing

    parser = argparse.ArgumentParser(description="Judge one result and show the verdict.")
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--version", choices=ALL_VERSIONS, default="v3")
    args = parser.parse_args()

    with engine.connect() as conn:
        row = conn.execute(
            text(f"{RESULT_QUERY.text} WHERE r.run_id = :run_id AND r.task_id = :task_id"),
            {"run_id": args.run, "task_id": args.task},
        ).mappings().first()
    if row is None:
        parser.error(f"No result for task {args.task} in run {args.run}.")

    tracing = setup_tracing()
    unload_other_models(keep=settings.judge_model)
    provider = judge_provider()
    record = judge_result(provider, get_budget_guard(provider.name), dict(row), args.version)

    print(f"Judge's reasoning:\n{record['reasoning']}\n")
    for key, value in record.items():
        if isinstance(value, bool) and key != "passed":
            print(f"  {key}: {value}")
    print(f"\nfailure_category: {record['failure_category']}")
    print("VERDICT:", "PASS" if record["passed"] else "FAIL")
    tracing.force_flush()