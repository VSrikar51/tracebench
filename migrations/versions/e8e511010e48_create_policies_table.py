"""create policies table

Revision ID: e8e511010e48
Revises: c7f978ce55b8
Create Date: 2026-10-10 22:46:50.708129

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8e511010e48'
down_revision: Union[str, Sequence[str], None] = 'c7f978ce55b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE store.policies (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            body           TEXT NOT NULL,
            search_vector  TSVECTOR GENERATED ALWAYS AS (
                setweight(to_tsvector('english', title), 'A') ||
                setweight(to_tsvector('english', body), 'B')
            ) STORED
        )
    """)

    op.execute("CREATE INDEX ON store.policies USING GIN (search_vector)")


def downgrade() -> None:
    op.execute("DROP TABLE store.policies")
