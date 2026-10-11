"""create evals tables

Revision ID: f6a9ef38e685
Revises: 1fba1f804b3f
Create Date: 2026-10-11 12:38:38.683129

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a9ef38e685'
down_revision: Union[str, Sequence[str], None] = '1fba1f804b3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FAILURE_CATEGORIES = """(
    'wrong_tool', 'missing_tool_call', 'bad_arguments', 'wrong_outcome',
    'hallucination', 'policy_violation', 'escalation_error', 'no_clarification',
    'injection_followed', 'poor_response', 'system_error'
)"""


def upgrade() -> None:
    op.execute("""
        CREATE TABLE evals.tasks (
            dataset_version  TEXT NOT NULL,
            id               TEXT NOT NULL,
            category         TEXT NOT NULL,
            message          TEXT NOT NULL,
            smoke            BOOLEAN NOT NULL,
            expected         JSONB NOT NULL,
            notes            TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (dataset_version, id)
        )
    """)

    op.execute("""
        CREATE TABLE evals.runs (
            id               INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            label            TEXT NOT NULL,
            dataset_version  TEXT NOT NULL,
            smoke_only       BOOLEAN NOT NULL,
            agent_provider   TEXT NOT NULL,
            agent_model      TEXT NOT NULL,
            judge_model      TEXT,
            git_commit       TEXT,
            config           JSONB NOT NULL DEFAULT '{}',
            status           TEXT NOT NULL DEFAULT 'running'
                             CHECK (status IN ('running', 'completed', 'failed')),
            started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at      TIMESTAMPTZ
        )
    """)

    op.execute(f"""
        CREATE TABLE evals.results (
            id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id            INTEGER NOT NULL REFERENCES evals.runs (id) ON DELETE CASCADE,
            dataset_version   TEXT NOT NULL,
            task_id           TEXT NOT NULL,
            trace_id          TEXT,
            reply             TEXT NOT NULL,
            stop_reason       TEXT NOT NULL,
            steps             INTEGER NOT NULL,
            input_tokens      INTEGER NOT NULL,
            output_tokens     INTEGER NOT NULL,
            cost_usd          NUMERIC(12, 6) NOT NULL,
            duration_ms       DOUBLE PRECISION NOT NULL,
            code_checks       JSONB NOT NULL DEFAULT '{{}}',
            code_passed       BOOLEAN,
            judge_verdict     JSONB,
            judge_passed      BOOLEAN,
            passed            BOOLEAN,
            failure_category  TEXT CHECK (failure_category IN {FAILURE_CATEGORIES}),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            FOREIGN KEY (dataset_version, task_id) REFERENCES evals.tasks (dataset_version, id),
            UNIQUE (run_id, task_id)
        )
    """)
    op.execute("CREATE INDEX ON evals.results (task_id)")

    op.execute(f"""
        CREATE TABLE evals.human_labels (
            id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            result_id         INTEGER NOT NULL REFERENCES evals.results (id) ON DELETE CASCADE,
            labeler           TEXT NOT NULL,
            passed            BOOLEAN NOT NULL,
            failure_category  TEXT CHECK (failure_category IN {FAILURE_CATEGORIES}),
            notes             TEXT NOT NULL DEFAULT '',
            labeled_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (result_id, labeler),
            CHECK (passed OR failure_category IS NOT NULL)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE evals.human_labels")
    op.execute("DROP TABLE evals.results")
    op.execute("DROP TABLE evals.runs")
    op.execute("DROP TABLE evals.tasks")
