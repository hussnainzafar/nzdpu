"""update_wis_user_request

Revision ID: 18f83ebe22a4
Revises: 8b8b6eb48227
Create Date: 2024-08-16 11:04:53.613062

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "18f83ebe22a4"
down_revision = "8b8b6eb48227"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "wis_user_request",
        "status",
        existing_type=sa.VARCHAR(),
        type_=sa.Enum(
            "REQUESTED", "APPROVED", "REJECTED", name="userpublisherstatusenum"
        ),
        existing_nullable=False,
        postgresql_using="status::userpublisherstatusenum",
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "wis_user_request",
        "status",
        existing_type=sa.Enum(
            "REQUESTED", "APPROVED", "REJECTED", name="userpublisherstatusenum"
        ),
        type_=sa.VARCHAR(),
        existing_nullable=False,
    )
    # ### end Alembic commands ###
