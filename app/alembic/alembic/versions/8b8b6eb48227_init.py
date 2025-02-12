"""init

Revision ID: 8b8b6eb48227
Revises:
Create Date: 2024-08-16 11:03:53.550787

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8b8b6eb48227"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = inspector.get_table_names()

    has_wis_tables = False
    for table in tables:
        if table.startswith("wis"):
            has_wis_tables = True
            break

    # we have to skip this migration because it is already applied
    if has_wis_tables:
        op.drop_table("alembic_version")
        alembic_version = op.create_table(
            "alembic_version",
            sa.Column("version_num", sa.String(length=32), nullable=False),
        )
        sa.insert(alembic_version).values(version_num="8b8b6eb48227")
        return

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "wis_choice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("choice_id", sa.Integer(), nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("set_name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=True),
        sa.Column("language_code", sa.String(length=25), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "choice_id",
            "set_id",
            "set_name",
            "language_code",
            name="_choice_set_lang_unique",
        ),
    )
    op.create_table(
        "wis_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "wis_group",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("delegate_user_id", sa.Integer(), nullable=True),
        sa.Column("delegate_group_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "wis_organization",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lei", sa.String(), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("last_updated_on", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("legal_name", sa.String(), nullable=False),
        sa.Column("jurisdiction", sa.String(), nullable=True),
        sa.Column("company_website", sa.String(), nullable=True),
        sa.Column("headquarter_address_lines", sa.String(), nullable=True),
        sa.Column("headquarter_address_number", sa.String(), nullable=True),
        sa.Column("headquarter_city", sa.String(), nullable=True),
        sa.Column("headquarter_country", sa.String(), nullable=True),
        sa.Column("headquarter_language", sa.String(), nullable=True),
        sa.Column("headquarter_postal_code", sa.String(), nullable=True),
        sa.Column("headquarter_region", sa.String(), nullable=True),
        sa.Column("legal_address_lines", sa.String(), nullable=True),
        sa.Column("legal_address_number", sa.String(), nullable=True),
        sa.Column("legal_city", sa.String(), nullable=True),
        sa.Column("legal_country", sa.String(), nullable=True),
        sa.Column("legal_language", sa.String(), nullable=True),
        sa.Column("legal_postal_code", sa.String(), nullable=True),
        sa.Column("legal_region", sa.String(), nullable=True),
        sa.Column("sics_sector", sa.String(), nullable=True),
        sa.Column("sics_sub_sector", sa.String(), nullable=True),
        sa.Column("sics_industry", sa.String(), nullable=True),
        sa.Column("company_type", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lei"),
    )
    op.create_index(
        "idx_org_legal", "wis_organization", ["legal_name"], unique=False
    )
    op.create_index(
        op.f("ix_wis_organization_jurisdiction"),
        "wis_organization",
        ["jurisdiction"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wis_organization_legal_name"),
        "wis_organization",
        ["legal_name"],
        unique=False,
    )

    op.create_table(
        "wis_password_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("encrypted_password", sa.String(length=256), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "wis_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("api_key", sa.String(length=256), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("password", sa.String(length=256), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("last_access", sa.DateTime(), nullable=True),
        sa.Column("refresh_token_uid", sa.String(), nullable=True),
        sa.Column("token_iat", sa.DateTime(), nullable=True),
        sa.Column("auth_mode", sa.String(), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("organization_name", sa.String(), nullable=True),
        sa.Column("organization_type", sa.String(), nullable=True),
        sa.Column("jurisdiction", sa.String(), nullable=True),
        sa.Column("data_last_accessed", sa.DateTime(), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("notifications", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "wis_user_organization_id_idx",
        "wis_user",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "wis_vault",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("storage_type", sa.Integer(), nullable=False),
        sa.Column("access_type", sa.String(length=256), nullable=False),
        sa.Column("access_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "wis_file_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("value_id", sa.Integer(), nullable=True),
        sa.Column("vault_id", sa.Integer(), nullable=True),
        sa.Column("vault_obj_id", sa.Text(), nullable=True),
        sa.Column("view_id", sa.Integer(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("vault_path", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("md5", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["vault_id"], ["wis_vault.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_file_registry_vault_id_idx",
        "wis_file_registry",
        ["vault_id"],
        unique=False,
    )
    op.create_table(
        "wis_permission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("grant", sa.Boolean(), nullable=False),
        sa.Column("list", sa.Boolean(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("write", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["wis_group.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["wis_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_permission_group_id_idx",
        "wis_permission",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        "wis_permission_user_id_idx",
        "wis_permission",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "wis_table_def",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("heritable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["wis_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "wis_table_def_user_id_idx", "wis_table_def", ["user_id"], unique=False
    )
    op.create_table(
        "wis_user_group",
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["wis_group.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["wis_user.id"],
        ),
        sa.UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )
    op.create_index(
        "wis_user_group_group_id_idx",
        "wis_user_group",
        ["group_id"],
        unique=False,
    )
    op.create_table(
        "wis_user_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "REQUESTED",
                "APPROVED",
                "REJECTED",
                name="userpublisherstatusenum",
            ),
            nullable=False,
        ),
        sa.Column("linkedin_link", sa.String(), nullable=True),
        sa.Column("company_lei", sa.String(), nullable=False),
        sa.Column("company_type", sa.String(), nullable=True),
        sa.Column("company_website", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["wis_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_user_request_user_id_idx",
        "wis_user_request",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "wis_column_def",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("table_def_id", sa.Integer(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("attribute_type", sa.String(length=25), nullable=False),
        sa.Column("attribute_type_id", sa.Integer(), nullable=True),
        sa.Column("choice_set_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["table_def_id"], ["wis_table_def.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["wis_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "wis_column_def_table_def_id_idx",
        "wis_column_def",
        ["table_def_id"],
        unique=False,
    )
    op.create_index(
        "wis_column_def_user_id_idx",
        "wis_column_def",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "wis_table_view",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_def_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("permissions_set_id", sa.Integer(), nullable=True),
        sa.Column("constraint_view", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["table_def_id"], ["wis_table_def.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["wis_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_table_view_table_def_id_idx",
        "wis_table_view",
        ["table_def_id"],
        unique=False,
    )
    op.create_index(
        "wis_table_view_user_id_idx",
        "wis_table_view",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "wis_attribute_prompt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("column_def_id", sa.Integer(), nullable=True),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language_code", sa.String(length=25), nullable=True),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["column_def_id"], ["wis_column_def.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_attribute_prompt_column_def_id_idx",
        "wis_attribute_prompt",
        ["column_def_id"],
        unique=False,
    )
    op.create_table(
        "wis_column_view",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("column_def_id", sa.Integer(), nullable=True),
        sa.Column("table_view_id", sa.Integer(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("permissions_set_id", sa.Integer(), nullable=True),
        sa.Column("constraint_value", sa.JSON(), nullable=True),
        sa.Column("constraint_view", sa.JSON(), nullable=True),
        sa.Column("choice_set_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["column_def_id"], ["wis_column_def.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["table_view_id"], ["wis_table_view.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["wis_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_column_view_column_def_id_idx",
        "wis_column_view",
        ["column_def_id"],
        unique=False,
    )
    op.create_index(
        "wis_column_view_table_view_id_idx",
        "wis_column_view",
        ["table_view_id"],
        unique=False,
    )
    op.create_index(
        "wis_column_view_user_id_idx",
        "wis_column_view",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "wis_obj",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_view_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("activated_on", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("checked_out", sa.Boolean(), nullable=False),
        sa.Column("checked_out_on", sa.DateTime(), nullable=True),
        sa.Column("permissions_set_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column("data_source", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "PUBLISHED", "BLANK", name="submissionobjstatusenum"
            ),
            nullable=True,
        ),
        sa.Column("lei", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["wis_user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["table_view_id"], ["wis_table_view.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["wis_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("lei_idx", "wis_obj", ["lei"], unique=False)
    op.create_index(
        "wis_obj_data_source", "wis_obj", ["data_source"], unique=False
    )
    op.create_index(
        "wis_obj_submitted_by_idx", "wis_obj", ["submitted_by"], unique=False
    )
    op.create_index(
        "wis_obj_table_view_id_idx", "wis_obj", ["table_view_id"], unique=False
    )
    op.create_index(
        "wis_obj_user_id_idx", "wis_obj", ["user_id"], unique=False
    )
    op.create_table(
        "wis_restatement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("obj_id", sa.Integer(), nullable=False),
        sa.Column("attribute_name", sa.String(), nullable=False),
        sa.Column("attribute_row", sa.Integer(), nullable=False),
        sa.Column("reason_for_restatement", sa.String(), nullable=True),
        sa.Column("data_source", sa.Integer(), nullable=True),
        sa.Column("reporting_datetime", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["obj_id"],
            ["wis_obj.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "wis_restatement_obj_id_idx",
        "wis_restatement",
        ["obj_id"],
        unique=False,
    )

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("wis_restatement_obj_id_idx", table_name="wis_restatement")
    op.drop_table("wis_restatement")
    op.drop_index("wis_obj_user_id_idx", table_name="wis_obj")
    op.drop_index("wis_obj_table_view_id_idx", table_name="wis_obj")
    op.drop_index("wis_obj_submitted_by_idx", table_name="wis_obj")
    op.drop_index("wis_obj_data_source", table_name="wis_obj")
    op.drop_index("lei_idx", table_name="wis_obj")
    op.drop_table("wis_obj")
    op.drop_index("wis_column_view_user_id_idx", table_name="wis_column_view")
    op.drop_index(
        "wis_column_view_table_view_id_idx", table_name="wis_column_view"
    )
    op.drop_index(
        "wis_column_view_column_def_id_idx", table_name="wis_column_view"
    )
    op.drop_table("wis_column_view")
    op.drop_index(
        "wis_attribute_prompt_column_def_id_idx",
        table_name="wis_attribute_prompt",
    )
    op.drop_table("wis_attribute_prompt")
    op.drop_index("wis_table_view_user_id_idx", table_name="wis_table_view")
    op.drop_index(
        "wis_table_view_table_def_id_idx", table_name="wis_table_view"
    )
    op.drop_table("wis_table_view")
    op.drop_index("wis_column_def_user_id_idx", table_name="wis_column_def")
    op.drop_index(
        "wis_column_def_table_def_id_idx", table_name="wis_column_def"
    )
    op.drop_table("wis_column_def")
    op.drop_index(
        "wis_user_request_user_id_idx", table_name="wis_user_request"
    )
    op.drop_table("wis_user_request")
    op.drop_index("wis_user_group_group_id_idx", table_name="wis_user_group")
    op.drop_table("wis_user_group")
    op.drop_index("wis_table_def_user_id_idx", table_name="wis_table_def")
    op.drop_table("wis_table_def")
    op.drop_index("wis_permission_user_id_idx", table_name="wis_permission")
    op.drop_index("wis_permission_group_id_idx", table_name="wis_permission")
    op.drop_table("wis_permission")
    op.drop_index(
        "wis_file_registry_vault_id_idx", table_name="wis_file_registry"
    )
    op.drop_table("wis_file_registry")
    op.drop_table("wis_vault")
    op.drop_index("wis_user_organization_id_idx", table_name="wis_user")
    op.drop_table("wis_user")
    op.drop_table("wis_password_history")

    op.drop_index(
        op.f("ix_wis_organization_legal_name"), table_name="wis_organization"
    )
    op.drop_index(
        op.f("ix_wis_organization_jurisdiction"), table_name="wis_organization"
    )
    op.drop_index("idx_org_legal", table_name="wis_organization")
    op.drop_table("wis_organization")
    op.drop_table("wis_group")
    op.drop_table("wis_config")
    op.drop_table("wis_choice")

    conn = op.get_bind()

    conn.execute(sa.text("DROP TYPE userpublisherstatusenum;"))
    conn.execute(sa.text("DROP TYPE submissionobjstatusenum;"))

    # ### end Alembic commands ###
