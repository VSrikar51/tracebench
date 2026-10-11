"""create telemetry tables

Revision ID: 1fba1f804b3f
Revises: e8e511010e48
Create Date: 2026-10-11 11:53:40.592176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fba1f804b3f'
down_revision: Union[str, Sequence[str], None] = 'e8e511010e48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE TABLE telemetry.spans (
            span_id         TEXT PRIMARY KEY,
            trace_id        TEXT NOT NULL,
            parent_span_id  TEXT,
            name            TEXT NOT NULL,
            kind            TEXT NOT NULL,
            start_time      TIMESTAMPTZ NOT NULL,
            end_time        TIMESTAMPTZ NOT NULL,
            duration_ms     DOUBLE PRECISION GENERATED ALWAYS AS (
                EXTRACT(EPOCH FROM (end_time - start_time)) * 1000
            ) STORED,
            status          TEXT NOT NULL CHECK (status IN ('unset', 'ok', 'error')),
            status_message  TEXT,
            attributes      JSONB NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX ON telemetry.spans (trace_id)")
    op.execute("CREATE INDEX ON telemetry.spans (start_time)")

    op.execute("""
        CREATE TABLE telemetry.llm_calls (
            span_id         TEXT PRIMARY KEY
                            REFERENCES telemetry.spans (span_id) ON DELETE CASCADE,
            trace_id        TEXT NOT NULL,
            provider        TEXT NOT NULL,
            model           TEXT NOT NULL,
            input_tokens    INTEGER NOT NULL,
            output_tokens   INTEGER NOT NULL,
            cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0,
            finish_reason   TEXT,
            input_messages  JSONB,
            output_message  JSONB
        )
    """)
    op.execute("CREATE INDEX ON telemetry.llm_calls (trace_id)")

    op.execute("""
        CREATE TABLE telemetry.tool_calls (
            span_id        TEXT PRIMARY KEY
                           REFERENCES telemetry.spans (span_id) ON DELETE CASCADE,
            trace_id       TEXT NOT NULL,
            tool_name      TEXT NOT NULL,
            call_id        TEXT,
            arguments      JSONB,
            result         JSONB,
            success        BOOLEAN NOT NULL,
            error_message  TEXT
        )
    """)
    op.execute("CREATE INDEX ON telemetry.tool_calls (trace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE telemetry.tool_calls")
    op.execute("DROP TABLE telemetry.llm_calls")
    op.execute("DROP TABLE telemetry.spans")
