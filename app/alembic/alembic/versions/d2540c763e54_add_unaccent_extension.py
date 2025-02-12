"""Add unaccent extension

Revision ID: d2540c763e54
Revises: ec884e2525db
Create Date: 2024-10-30 09:40:09.787171

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2540c763e54"
down_revision = "ec884e2525db"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("CREATE EXTENSION unaccent;"))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP EXTENSION unaccent;"))
