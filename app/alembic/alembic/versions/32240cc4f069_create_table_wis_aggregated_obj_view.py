"""create_table_wis_aggregated_obj_view

Revision ID: 32240cc4f069
Revises: 103e230b8024
Create Date: 2024-08-16 12:24:19.798266

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "32240cc4f069"
down_revision = "103e230b8024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "wis_aggregated_obj_view",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_def_id", sa.Integer(), nullable=False),
        sa.Column("obj_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["obj_id"], ["wis_obj.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["table_def_id"], ["wis_table_def.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("wis_aggregated_obj_view")
    # ### end Alembic commands ###
