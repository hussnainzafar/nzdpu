"""Add extensions for fuzzy search

Revision ID: 9602b11e94f6
Revises: 9414cf243f42
Create Date: 2024-09-04 08:19:09.341182

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9602b11e94f6"
down_revision = "820a33a33166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("CREATE EXTENSION pg_trgm;"))
    conn.execute(sa.text("CREATE EXTENSION fuzzystrmatch;"))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP EXTENSION pg_trgm;"))
    conn.execute(sa.text("DROP EXTENSION fuzzystrmatch;"))
