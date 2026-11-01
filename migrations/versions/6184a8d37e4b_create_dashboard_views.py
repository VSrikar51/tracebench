"""create dashboard views

Revision ID: 6184a8d37e4b
Revises: a152ee88bf99
Create Date: 2026-11-01 12:26:40.024530

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6184a8d37e4b'
down_revision: Union[str, Sequence[str], None] = 'a152ee88bf99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW evals.run_summary AS
        SELECT
            ru.id AS run_id,
            ru.label,
            ru.started_at,
            ru.status,
            ru.agent_model,
            ru.judge_model,
            ru.dataset_version,
            ru.smoke_only,
            ru.git_commit,
            count(re.id) AS tasks,
            avg(re.code_passed::int) AS code_pass_rate,
            avg(re.passed::int) AS final_pass_rate,
            avg(re.steps) AS avg_steps,
            avg(re.duration_ms) / 1000 AS avg_seconds,
            sum(re.cost_usd) AS total_cost_usd,
            sum(re.input_tokens + re.output_tokens) AS total_tokens
        FROM evals.runs AS ru
        LEFT JOIN evals.results AS re ON re.run_id = ru.id
        GROUP BY ru.id
    """)

    op.execute("""
        CREATE VIEW evals.citation_rates AS
        SELECT
            re.run_id,
            count(*) AS citations_expected,
            count(*) FILTER (WHERE (c.value ->> 'passed')::boolean) AS citations_made,
            avg((c.value ->> 'passed')::boolean::int) AS citation_rate
        FROM evals.results AS re
        CROSS JOIN LATERAL jsonb_each(re.code_checks) AS c(key, value)
        WHERE NOT (c.value ->> 'hard')::boolean
        GROUP BY re.run_id
    """)

    op.execute("""
        CREATE VIEW evals.category_scores AS
        SELECT
            re.run_id,
            t.category,
            count(*) AS tasks,
            count(*) FILTER (WHERE re.passed) AS passed,
            avg(re.passed::int) AS pass_rate
        FROM evals.results AS re
        JOIN evals.tasks AS t
          ON t.id = re.task_id AND t.dataset_version = re.dataset_version
        GROUP BY re.run_id, t.category
    """)

    op.execute("""
        CREATE VIEW evals.failure_breakdown AS
        SELECT run_id, failure_category, count(*) AS failures
        FROM evals.results
        WHERE passed = false
        GROUP BY run_id, failure_category
    """)

    op.execute("""
        CREATE VIEW evals.labeled_results AS
        SELECT
            re.run_id,
            re.id AS result_id,
            re.task_id,
            t.category,
            h.labeler,
            h.passed AS human_passed,
            h.failure_category AS human_category,
            re.code_passed,
            re.judge_passed,
            re.passed AS final_passed,
            re.failure_category AS final_category
        FROM evals.human_labels AS h
        JOIN evals.results AS re ON re.id = h.result_id
        JOIN evals.tasks AS t
          ON t.id = re.task_id AND t.dataset_version = re.dataset_version
    """)

    op.execute("""
        CREATE VIEW telemetry.step_spans AS
        SELECT
            s.span_id,
            s.trace_id,
            s.start_time,
            s.duration_ms,
            s.status,
            s.attributes ->> 'gen_ai.operation.name' AS operation,
            CASE s.attributes ->> 'gen_ai.operation.name'
                WHEN 'chat' THEN 'model: ' || l.model
                WHEN 'execute_tool' THEN 'tool: ' || tc.tool_name
                ELSE s.name
            END AS step,
            l.input_tokens,
            l.output_tokens,
            l.cost_usd,
            tc.success AS tool_success
        FROM telemetry.spans AS s
        LEFT JOIN telemetry.llm_calls AS l USING (span_id)
        LEFT JOIN telemetry.tool_calls AS tc USING (span_id)
    """)

    op.execute("""
        CREATE VIEW telemetry.agent_runs AS
        SELECT
            s.trace_id,
            s.start_time,
            s.duration_ms,
            s.status,
            s.attributes ->> 'gen_ai.request.model' AS model,
            (s.attributes ->> 'tracebench.agent.steps')::int AS steps,
            s.attributes ->> 'tracebench.agent.stop_reason' AS stop_reason,
            (s.attributes ->> 'gen_ai.usage.input_tokens')::int AS input_tokens,
            (s.attributes ->> 'gen_ai.usage.output_tokens')::int AS output_tokens,
            (s.attributes ->> 'tracebench.cost_usd')::numeric AS cost_usd,
            re.run_id,
            re.task_id,
            re.passed,
            re.failure_category
        FROM telemetry.spans AS s
        LEFT JOIN evals.results AS re ON re.trace_id = s.trace_id
        WHERE s.attributes ->> 'gen_ai.operation.name' = 'invoke_agent'
    """)


def downgrade() -> None:
    op.execute("DROP VIEW telemetry.agent_runs")
    op.execute("DROP VIEW telemetry.step_spans")
    op.execute("DROP VIEW evals.labeled_results")
    op.execute("DROP VIEW evals.failure_breakdown")
    op.execute("DROP VIEW evals.category_scores")
    op.execute("DROP VIEW evals.citation_rates")
    op.execute("DROP VIEW evals.run_summary")
