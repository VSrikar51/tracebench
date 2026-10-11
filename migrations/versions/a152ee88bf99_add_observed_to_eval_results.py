"""add observed to eval results

Revision ID: a152ee88bf99
Revises: f6a9ef38e685
Create Date: 2026-10-11 14:01:15.971586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a152ee88bf99'
down_revision: Union[str, Sequence[str], None] = 'f6a9ef38e685'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE evals.results ADD COLUMN observed JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE evals.results DROP COLUMN observed")
