"""Add nz_id foreign key in submissions table

Revision ID: 9414cf243f42
Revises: 32240cc4f069
Create Date: 2024-08-19 13:02:03.802145

"""

from typing import Dict, Sequence, Tuple

import sqlalchemy as sa
from alembic import op

from app.db.models import Organization, SubmissionObj

# revision identifiers, used by Alembic.
revision = "9414cf243f42"
down_revision = "32240cc4f069"
branch_labels = None
depends_on = None


def get_organizations(
    conn: sa.Connection,
) -> Sequence[sa.Row[Tuple[Organization]]]:
    organization_query = sa.select(Organization)
    organizations_res = conn.execute(organization_query)
    return organizations_res.fetchall()


def get_lei_nz_id_mapper(
    organizations: Sequence[sa.Row[Tuple[Organization]]],
) -> Dict[str, int]:
    lei_to_nz_id_dict: Dict[str, int] = {}

    for organization in organizations:
        lei_to_nz_id_dict[organization[2]] = organization[1]

    return lei_to_nz_id_dict


def get_submissions(
    conn: sa.Connection,
) -> Sequence[sa.Row[Tuple[SubmissionObj]]]:
    submission_query = sa.select(SubmissionObj.id, SubmissionObj.lei)
    submissions_res = conn.execute(submission_query)
    return submissions_res.fetchall()


def migrate_lei_to_nz_id_in_submission(
    submissions: Sequence[sa.Row[Tuple[SubmissionObj]]],
    lei_to_nz_id: Dict[str, int],
):
    for submission in submissions:
        op.execute(
            sa.text(
                f"UPDATE wis_obj SET nz_id = {lei_to_nz_id[submission[1]]} WHERE id = {submission[0]};"
            )
        )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("wis_obj", sa.Column("nz_id", sa.Integer(), nullable=True))

    conn = op.get_bind()

    organizations = get_organizations(conn)
    lei_to_nz_id = get_lei_nz_id_mapper(organizations)

    submissions = get_submissions(conn)
    migrate_lei_to_nz_id_in_submission(submissions, lei_to_nz_id)

    op.alter_column(
        "wis_obj", sa.Column("nz_id", sa.Integer(), nullable=False)
    )

    op.create_foreign_key(
        "wis_obj_nz_id_fkey",
        "wis_obj",
        "wis_organization",
        ["nz_id"],
        ["nz_id"],
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("wis_obj_nz_id_fkey", "wis_obj", type_="foreignkey")
    op.drop_column("wis_obj", "nz_id")
    # ### end Alembic commands ###
