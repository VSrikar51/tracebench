"""Create Schemas

Revision ID: f1c621153ab0
Revises: 
Create Date: 2026-10-10 17:22:44.777132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c621153ab0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA store")
    op.execute("CREATE SCHEMA telemetry")
    op.execute("CREATE SCHEMA evals")


def downgrade() -> None:
    op.execute("DROP SCHEMA evals")
    op.execute("DROP SCHEMA telemetry")
    op.execute("DROP SCHEMA store")
