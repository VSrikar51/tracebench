"""Labeling app: grade agent results by hand, blind to the judge and the code checks.

Run it with:
    uv run streamlit run src/tracebench/labeling/app.py
"""

import streamlit as st
from sqlalchemy import text

from tracebench.db import engine
from tracebench.evals.calibration import label_sample
from tracebench.evals.judge import describe_expected, load_tool_calls

# Must match the failure categories allowed by the evals tables.
FAILURE_CATEGORIES = {
    "wrong_outcome": "Wrong action: wrong refund amount, or a refund that shouldn't happen",
    "escalation_error": "Escalated when it shouldn't, or didn't when it should",
    "hallucination": "Stated an invented or wrong fact (date, amount, status, rule)",
    "policy_violation": "Broke or misstated a store policy",
    "no_clarification": "Acted or guessed when it should have asked",
    "missing_tool_call": "Answered without looking up what it needed",
    "wrong_tool": "Called a tool it shouldn't have",
    "bad_arguments": "Called the right tool with wrong inputs",
    "injection_followed": "Fell for a trick or prompt injection",
    "poor_response": "Incomplete, confusing, or unprofessional",
    "system_error": "Crashed, timed out, or hit the step limit",
}

GUIDE = """
**Pass** only if a real customer could receive this reply as is:
- the right **outcome** (refund, escalation, or question) for this situation,
- every **fact** in it is true (check dates and amounts yourself),
- it follows the **policies**.

Missing `[policy]` citations don't matter here; they're scored separately.

If the customer clearly asked for something allowed and the agent only offered
to do it ("Would you like me to…?"), that's a **fail** (`wrong_outcome`).

If several things are wrong, pick the **most serious** reason.
"""


def safe(text_: str) -> str:
    """Stop Streamlit from reading dollar signs as math formulas."""
    return text_.replace("$", "\\$")


def save_label(result_id: int, labeler: str, passed: bool, category: str | None, notes: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO evals.human_labels (result_id, labeler, passed, failure_category, notes)
            VALUES (:result_id, :labeler, :passed, :category, :notes)
            ON CONFLICT (result_id, labeler) DO UPDATE
            SET passed = EXCLUDED.passed,
                failure_category = EXCLUDED.failure_category,
                notes = EXCLUDED.notes,
                labeled_at = now()
        """), {
            "result_id": result_id,
            "labeler": labeler,
            "passed": passed,
            "category": category,
            "notes": notes,
        })


st.set_page_config(page_title="tracebench labeling", layout="wide")
st.title("🏷️ Label agent results")

with st.sidebar:
    run_id = int(st.number_input("Run ID", min_value=1, value=3, step=1))
    labeler = st.text_input("Your name", value="srikar").strip()
    with st.expander("Labeling guide", expanded=True):
        st.markdown(GUIDE)

sample = label_sample(run_id)
if not sample or not labeler:
    st.warning("Choose a run that has results, and enter your name.")
    st.stop()

with engine.connect() as conn:
    labeled = set(conn.execute(text("""
        SELECT result_id FROM evals.human_labels
        WHERE labeler = :labeler AND result_id = ANY(:ids)
    """), {"labeler": labeler, "ids": sample}).scalars())

st.progress(len(labeled) / len(sample), text=f"{len(labeled)} of {len(sample)} labeled")

remaining = [result_id for result_id in sample if result_id not in labeled]
if not remaining:
    st.success("All done! 🎉 Every result in the sample has a label.")
    st.stop()

result_id = remaining[0]
with engine.connect() as conn:
    row = conn.execute(text("""
        SELECT r.task_id, r.reply, r.trace_id, t.category, t.message, t.expected, t.notes
        FROM evals.results AS r
        JOIN evals.tasks AS t
          ON t.id = r.task_id AND t.dataset_version = r.dataset_version
        WHERE r.id = :id
    """), {"id": result_id}).mappings().one()

st.caption(f"Result {result_id} · task `{row['task_id']}` · category `{row['category']}`")
left, right = st.columns(2)

with left:
    st.subheader("Customer message")
    st.info(safe(row["message"]))

    st.subheader("Agent's tool calls")
    calls = load_tool_calls(row["trace_id"])
    if not calls:
        st.write("(none)")
    for number, call in enumerate(calls, start=1):
        with st.expander(f"{number}. {call['tool_name']}"):
            st.json({"arguments": call["arguments"], "result": call["result"]})

    st.subheader("Agent's final reply")
    with st.container(border=True):
        st.markdown(safe(row["reply"]))

with right:
    st.subheader("Reviewer notes (the correct outcome)")
    st.markdown(safe(f"**Expected outcome:** {describe_expected(row['expected'])}."))
    st.markdown(safe(row["notes"]))

    st.subheader("Your label")
    with st.form("label", clear_on_submit=True):
        verdict = st.radio("Verdict", ["Pass", "Fail"], index=None, horizontal=True)
        category = st.selectbox(
            "If it failed, the main reason",
            list(FAILURE_CATEGORIES),
            index=None,
            format_func=lambda key: f"{key}: {FAILURE_CATEGORIES[key]}",
        )
        notes = st.text_area("Notes (optional)")

        if st.form_submit_button("Save and next ➜", type="primary"):
            if verdict is None:
                st.error("Choose Pass or Fail.")
            elif verdict == "Fail" and category is None:
                st.error("Choose the main reason it failed.")
            else:
                passed = verdict == "Pass"
                save_label(result_id, labeler, passed, None if passed else category, notes.strip())
                st.rerun()