"""Database models"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Table,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy import (
    Enum as EnumColumn,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from .database import Base
from ..schemas.column_def import AttributeType
from ..schemas.enums import (
    SICSSectorEnum,
    SubmissionObjStatusEnum,
)

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class ConfigProperty(str, Enum):
    """
    Service configuration properties
    """

    # Existing property
    GENERAL_SYSTEM_EMAIL_ADDRESS = "general.system_email_address"

    # New properties
    DATA_EXPLORER_DOWNLOAD_ALL = "data_explorer.download_all"
    DATA_EXPLORER_DOWNLOAD_SAMPLE = "data_explorer.download_sample"
    DATA_EXPLORER_DOWNLOAD_NONE = "data_explorer.download_none"
    COMPANY_PROFILE_DOWNLOAD_ALL = "company_profile.download_all"
    COMPANY_PROFILE_DOWNLOAD_NONE = "company_profile.download_none"
    DATA_DOWNLOAD_SHOW_ALL = "data_download.show_all"
    DATA_DOWNLOAD_EXCLUDE_CLASSIFICATION = (
        "data_download.exclude_classification"
    )
    SECURITY_ENABLE_CAPTCHA = "security.enable_captcha"


class Config(Base):
    """
    Service configuration model
    """

    __tablename__ = "wis_config"

    TYPE_INTEGER = "Integer"
    TYPE_FLOAT = "Float"
    TYPE_JSON = "JSON"
    TYPE_STRING = "String"
    TYPE_BOOLEAN = "Boolean"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[int | float | bool | str | None] = mapped_column(Text())
    description: Mapped[str | None] = mapped_column(String(255))

    def __repr__(self):
        return f"{self.name}: {self.value}"


class AuthMode(str, Enum):
    """
    Authorization modes
    """

    LOCAL = "LOCAL"
    FIREBASE = "FIREBASE"


class AuthRole(str, Enum):
    """
    Authorization roles
    """

    ADMIN = "admin"
    DATA_EXPLORER = "data_explorer"
    DATA_PUBLISHER = "data_publisher"
    SCHEMA_EDITOR = "schema_editor"


# many-to-many relationship between users and groups
user_group = Table(
    "wis_user_group",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("wis_user.id")),
    Column("group_id", Integer, ForeignKey("wis_group.id")),
    UniqueConstraint("user_id", "group_id", name="uq_user_group"),
)

wis_user_group_group_id_idx = Index(
    "wis_user_group_group_id_idx", user_group.c.group_id
)


class Group(Base):
    """
    Group model
    """

    __tablename__ = "wis_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[AuthRole] = mapped_column(
        String(32), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    delegate_user_id: Mapped[int | None] = mapped_column(Integer)
    delegate_group_id: Mapped[int | None] = mapped_column(Integer)
    permissions = relationship(
        "Permission",
        lazy="select",
        backref=backref("permission_group", lazy="joined"),
    )

    def __repr__(self):
        return f"<Group {self.name}>"


class PasswordHistory(Base):
    """
    Table holding a user's five most recent passwords
    """

    __tablename__ = "wis_password_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    encrypted_password: Mapped[str | None] = mapped_column(String(256))
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    def __repr__(self):
        return f"<PasswordHistory {self.id}>"


class User(Base):
    """
    User account model
    """

    __tablename__ = "wis_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(256))
    email_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    api_key: Mapped[str | None] = mapped_column(String(256), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    password: Mapped[str | None] = mapped_column(String(256))
    created_on: Mapped[datetime] = mapped_column(default=datetime.now)
    last_access: Mapped[datetime | None] = mapped_column(DateTime)
    refresh_token_uid: Mapped[str | None] = mapped_column(default=str(uuid4()))
    token_iat: Mapped[datetime] = mapped_column(nullable=True)
    auth_mode: Mapped[str] = mapped_column(default=AuthMode.LOCAL.value)
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(Integer)
    organization_name: Mapped[str | None] = mapped_column(String)
    organization_type: Mapped[str | None] = mapped_column(String)
    jurisdiction: Mapped[str | None] = mapped_column(String)
    groups: Mapped[list[Group]] = relationship(
        "Group",
        lazy="selectin",
        secondary=user_group,
        backref=backref("users", lazy="joined"),
    )
    requests = relationship("UserPublisherRequest")
    data_last_accessed: Mapped[datetime | None] = mapped_column(
        default=datetime.now()
    )
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)

    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self):
        return (
            f"<User {self.name}"
            f" email={self.email}"
            f" email_verified={self.email_verified}"
            f" first_name={self.first_name}"
            f" last_name={self.last_name}"
            f" enabled={self.enabled}"
            f" auth_mode={self.auth_mode}>"
        )


wis_user_organization_id_idx = Index(
    "wis_user_organization_id_idx", User.organization_id, unique=False
)


class Permission(Base):
    """
    Represent a permission for a user to access a resource
    """

    __tablename__ = "wis_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    set_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("wis_user.id"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("wis_group.id"))
    grant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    list: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<Permission {self.id}>"


wis_permission_user_id_idx = Index(
    "wis_permission_user_id_idx", Permission.user_id
)
wis_permission_group_id_idx = Index(
    "wis_permission_group_id_idx", Permission.group_id
)


class TableDef(Base):
    """
    Table definition model
    """

    __tablename__ = "wis_table_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_user.id", ondelete="SET NULL")
    )
    heritable: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[list[TableView]] = relationship(
        lazy="select", back_populates="table_def"
    )
    columns: Mapped[list[ColumnDef]] = relationship(
        "ColumnDef",
        lazy="selectin",
        back_populates="table_def",
        order_by="ColumnDef.id",  # ensure the selectinload loads the items ordered by id to keep the attribute as in schema order
    )

    def __repr__(self):
        return f"<TableDef {self.name}>"


wis_table_def_user_id_idx = Index(
    "wis_table_def_user_id_idx", TableDef.user_id, unique=False
)


class AggregatedObjectView(Base):
    __tablename__ = "wis_aggregated_obj_view"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    obj_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_obj.id", ondelete="CASCADE")
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )


class TableView(Base):
    """
    Table view model
    """

    __tablename__ = "wis_table_view"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_def_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_table_def.id", ondelete="CASCADE")
    )
    table_def: Mapped[TableDef] = relationship(back_populates="views")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_id: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_user.id", ondelete="SET NULL"), nullable=True
    )
    permissions_set_id: Mapped[int | None] = mapped_column()
    constraint_view: Mapped[dict | None] = mapped_column(JSON)
    column_views: Mapped[list[ColumnView]] = relationship(
        "ColumnView",
        lazy="select",
        backref=backref("table_view", lazy="joined"),
    )
    submissions: Mapped[list[SubmissionObj]] = relationship(
        "SubmissionObj",
        lazy="select",
        back_populates="table_view",
    )

    def __repr__(self):
        return f"<TableView {self.name}>"


wis_table_view_user_id_idx = Index(
    "wis_table_view_user_id_idx", TableView.user_id
)
wis_table_view_table_def_id_idx = Index(
    "wis_table_view_table_def_id_idx", TableView.table_def_id
)


class ColumnDef(Base):
    """
    Attribute primary model
    """

    __tablename__ = "wis_column_def"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    table_def_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wis_table_def.id", ondelete="CASCADE"),
        nullable=True,
    )
    table_def: Mapped[TableDef] = relationship(back_populates="columns")
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_user.id", ondelete="SET NULL")
    )
    attribute_type: Mapped[AttributeType] = mapped_column(
        String(25), nullable=False
    )
    attribute_type_id: Mapped[int] = mapped_column(nullable=True)
    choice_set_id: Mapped[int | None] = mapped_column()
    views: Mapped[list[ColumnView]] = relationship(
        lazy="selectin", back_populates="column_def"
    )
    choices: Mapped[list[Choice]] = relationship(
        "Choice",
        back_populates="column",
        uselist=True,
        primaryjoin="Choice.set_id == ColumnDef.choice_set_id",
        foreign_keys="Choice.set_id",
    )
    prompts: Mapped[list[AttributePrompt]] = relationship(
        "AttributePrompt",
        lazy="select",
        backref=backref("column_def", lazy="joined"),
    )

    def __repr__(self):
        return (
            f"<ColumnDef {self.name}"
            f" table_def_id={self.table_def_id}"
            f" user_id={self.user_id}"
            f" attribute_type={self.attribute_type}"
            f" attribute_type_id={self.attribute_type_id}"
            f" choice_set_id={self.choice_set_id}>"
        )

    async def update(
        self,
        session: AsyncSession,
        name: str | None,
        table_def_id: int | None,
        user_id: int | None,
        attribute_type_id: int | None,
        choice_set_id: int | None,
    ) -> None:
        """
        Update column
        -------

        """
        self.name = name if name is not None else self.name
        self.table_def_id = (
            table_def_id if table_def_id is not None else self.table_def_id
        )
        self.user_id = user_id if user_id is not None else self.user_id
        self.attribute_type_id = (
            attribute_type_id
            if attribute_type_id is not None
            else self.attribute_type_id
        )
        self.choice_set_id = (
            choice_set_id if choice_set_id is not None else self.choice_set_id
        )
        await session.flush()


wis_column_def_user_id_idx = Index(
    "wis_column_def_user_id_idx", ColumnDef.user_id
)
wis_column_def_table_def_id_idx = Index(
    "wis_column_def_table_def_id_idx", ColumnDef.table_def_id
)


class ColumnView(Base):
    """
    Attribute instance model
    """

    __tablename__ = "wis_column_view"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    column_def_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_column_def.id", ondelete="CASCADE")
    )
    column_def: Mapped[ColumnDef] = relationship(back_populates="views")
    table_view_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_table_view.id", ondelete="CASCADE")
    )
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("wis_user.id"))
    permissions_set_id: Mapped[int | None] = mapped_column(Integer)
    constraint_value: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    constraint_view: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=True
    )
    choice_set_id: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self):
        return (
            f"<ColumnView {self.id}"
            f" column_def_id={self.column_def_id}"
            f" table_view_id={self.table_view_id}"
            f" user_id={self.user_id}"
            f" permissions_set_id={self.permissions_set_id}"
            f" constraint_value={self.constraint_value}"
            f" constraint_view={self.constraint_view}"
            f" choice_set_id={self.choice_set_id}>"
        )


wis_column_view_user_id_idx = Index(
    "wis_column_view_user_id_idx", ColumnView.user_id
)

wis_column_view_table_view_id_idx = Index(
    "wis_column_view_table_view_id_idx", ColumnView.table_view_id
)
wis_column_view_column_def_id_idx = Index(
    "wis_column_view_column_def_id_idx", ColumnView.column_def_id
)


class Choice(Base):
    """
    Choice model
    """

    __tablename__ = "wis_choice"

    CHOICE_ID_AUTO_START = 1000000

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    choice_id: Mapped[int] = mapped_column(Integer, nullable=False)
    set_id: Mapped[int] = mapped_column()
    column: Mapped[ColumnDef] = relationship(
        back_populates="choices",
        primaryjoin="Choice.set_id == ColumnDef.choice_set_id",
        foreign_keys=set_id,
    )
    set_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int | None] = mapped_column(Integer)
    language_code: Mapped[str | None] = mapped_column(String(25))

    __table_args__ = (
        UniqueConstraint(
            "choice_id",
            "set_id",
            "set_name",
            "language_code",
            name="_choice_set_lang_unique",
        ),
    )

    def __repr__(self):
        return (
            f"<Choice {self.id}"
            f" choice_id={self.choice_id}"
            f" set_id={self.set_id}"
            f" set_name={self.set_name}"
            f" value={self.value}"
            f" description={self.description}"
            f" order={self.order}"
            f" language_code={self.language_code}>"
        )


class AttributePrompt(Base):
    """
    Attribute prompt model
    """

    __tablename__ = "wis_attribute_prompt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    column_def_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_column_def.id", ondelete="CASCADE")
    )
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str | None] = mapped_column(String(25))
    role: Mapped[str | None] = mapped_column(String(255), default="label")

    def __repr__(self):
        return f"<AttributePrompt '{self.value}'>"


wis_attribute_prompt_column_def_id_idx = Index(
    "wis_attribute_prompt_column_def_id_idx", AttributePrompt.column_def_id
)


class SubmissionObj(Base):
    """
    Submission object model
    """

    __tablename__ = "wis_obj"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_view_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_table_view.id", ondelete="CASCADE")
    )
    table_view: Mapped[TableView] = relationship(
        "TableView", back_populates="submissions"
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wis_user.id", ondelete="SET NULL")
    )
    checked_out: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_out_on: Mapped[datetime | None] = mapped_column(DateTime)
    permissions_set_id: Mapped[int | None] = mapped_column(Integer)
    submitted_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_user.id"), nullable=False
    )
    data_source: Mapped[str | None] = mapped_column(Text)
    user = relationship("User", backref="submissions", foreign_keys=[user_id])
    status: Mapped[SubmissionObjStatusEnum | None] = mapped_column(
        EnumColumn(
            SubmissionObjStatusEnum,
        )
    )
    lei: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_organization.nz_id")
    )

    def __repr__(self):
        return (
            f"<SubmissionObj {self.name}"
            f" id={self.id}"
            f" name={self.name}"
            f" revision={self.revision}"
            f" checked_out={self.checked_out}"
            ">"
        )


wis_obj_user_id_idx = Index("wis_obj_user_id_idx", SubmissionObj.user_id)
wis_obj_table_view_id_idx = Index(
    "wis_obj_table_view_id_idx", SubmissionObj.table_view_id
)
wis_obj_submitted_by_idx = Index(
    "wis_obj_submitted_by_idx", SubmissionObj.submitted_by
)
wis_obj_data_source = Index("wis_obj_data_source", SubmissionObj.data_source)
lei_idx = Index("lei_idx", SubmissionObj.lei)


class FileRegistry(Base):
    """
    File registry model
    """

    __tablename__ = "wis_file_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value_id: Mapped[int] = mapped_column(Integer, nullable=True)
    vault_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_vault.id", ondelete="SET NULL"), nullable=True
    )
    vault_obj_id: Mapped[str] = mapped_column(Text, nullable=True)
    view_id: Mapped[int] = mapped_column(Integer, nullable=True)
    created_on: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    vault_path: Mapped[str] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(Text, nullable=True)
    md5: Mapped[str] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<FileRegistry {self.id}>"


wis_file_registry_vault_id_idx = Index(
    "wis_file_registry_vault_id_idx", FileRegistry.vault_id
)


class Vault(Base):
    """
    Vault model
    """

    __tablename__ = "wis_vault"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    storage_type: Mapped[int] = mapped_column(Integer, nullable=False)
    access_type: Mapped[str] = mapped_column(String(256), nullable=False)
    access_data: Mapped[dict | None] = mapped_column(JSON)

    def __repr__(self):
        return f"<Vault {self.name}>"


class Organization(Base):
    """
    Organization model
    """

    __tablename__ = "wis_organization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nz_id: Mapped[int | None] = mapped_column(
        Integer,
        unique=True,
        index=True,
        default=Sequence("nz_id_seq", start=1000, increment=1),
    )
    lei: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    isics: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    duns: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    gleif: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    sing_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )

    created_on: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    last_updated_on: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legal_name: Mapped[str] = mapped_column(String, nullable=False, index=True)

    jurisdiction: Mapped[str | None] = mapped_column(String, index=True)
    company_website: Mapped[str | None] = mapped_column(String)

    headquarter_address_lines: Mapped[str | None] = mapped_column(String)
    headquarter_address_number: Mapped[str | None] = mapped_column(String)
    headquarter_city: Mapped[str | None] = mapped_column(String)
    headquarter_country: Mapped[str | None] = mapped_column(String)
    headquarter_language: Mapped[str | None] = mapped_column(String)
    headquarter_postal_code: Mapped[str | None] = mapped_column(String)
    headquarter_region: Mapped[str | None] = mapped_column(String)

    legal_address_lines: Mapped[str | None] = mapped_column(String)
    legal_address_number: Mapped[str | None] = mapped_column(String)
    legal_city: Mapped[str | None] = mapped_column(String)
    legal_country: Mapped[str | None] = mapped_column(String)
    legal_language: Mapped[str | None] = mapped_column(String)
    legal_postal_code: Mapped[str | None] = mapped_column(String)
    legal_region: Mapped[str | None] = mapped_column(String)

    sics_sector: Mapped[SICSSectorEnum | None] = mapped_column(String)
    sics_sub_sector: Mapped[str | None] = mapped_column(String)
    sics_industry: Mapped[str | None] = mapped_column(String)
    company_type: Mapped[str | None] = mapped_column(String)

    def __repr__(self):
        return f"<Organization {self.legal_name}>"


idx_org_legal = Index("idx_org_legal", Organization.legal_name, unique=False)


class OrganizationAlias(Base):
    """
    Organization alias model
    """

    __tablename__ = "wis_organization_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nz_id: Mapped[int | None] = mapped_column(
        ForeignKey("wis_organization.nz_id")
    )
    alias: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self):
        return (
            f"<OrganizationAlias id={self.id}, "
            f"nz_id={self.nz_id}, "
            f"alias='{self.alias}'>"
        )


class UserPublisherStatusEnum(str, Enum):
    """
    Enum for user request status.
    """

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserPublisherRequest(Base):
    """
    Table holding requests that users make (e.g. more privileges)
    """

    __tablename__ = "wis_user_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_user.id"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(String)
    status: Mapped[UserPublisherStatusEnum] = mapped_column(
        nullable=False, default=UserPublisherStatusEnum.REQUESTED.value
    )
    linkedin_link: Mapped[str | None] = mapped_column(String)
    company_lei: Mapped[str] = mapped_column(String, nullable=False)
    company_type: Mapped[str | None] = mapped_column(String)
    company_website: Mapped[str | None] = mapped_column(String)


wis_user_request_user_id_idx = Index(
    "wis_user_request_user_id_idx", UserPublisherRequest.user_id, unique=False
)


class Restatement(Base):
    """
    Restatement model
    """

    __tablename__ = "wis_restatement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    obj_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_obj.id"), nullable=False
    )
    # the id of original submission
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wis_obj.id"), nullable=False
    )
    attribute_name: Mapped[str] = mapped_column(String, nullable=False)
    attribute_row: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_for_restatement: Mapped[str | None] = mapped_column(String)
    data_source: Mapped[str | None] = mapped_column(String)
    reporting_datetime: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    @classmethod
    async def history(
        cls, session: AsyncSession, group_id: int
    ) -> Sequence[Restatement]:
        result = await session.scalars(
            select(cls).where(cls.group_id == group_id)
        )
        return result.all()

    def __repr__(self):
        return (
            f"<Restatement {self.id}"
            f" obj_id={self.obj_id}"
            f" group_id={self.group_id}"
            f" attribute_name={self.attribute_name}"
            f" attribute_row={self.attribute_row}"
            f" reason_for_restatement={self.reason_for_restatement}"
            f" data_source={self.data_source}"
            f" reporting_datetime={self.reporting_datetime}>"
        )


wis_restatement_obj_id_idx = Index(
    "wis_restatement_obj_id_idx", Restatement.obj_id
)

wis_restatement_group_id_idx = Index(
    "wis_restatement_group_id_idx", Restatement.group_id
)


class SourceEnum(str, Enum):
    WEB = "web"
    SCRIPT = "script"


class Tracking(Base):
    """
    Tracking model
    """

    __tablename__ = "wis_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String, nullable=False)
    date_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    source: Mapped[SourceEnum] = mapped_column(
        nullable=False, default=SourceEnum.WEB.value
    )
    result: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self):
        return (
            f"<Tracking id={self.id}, "
            f"email={self.user_email}, "
            f"api_endpoint='{self.api_endpoint}', "
            f"date_time='{self.date_time}', "
            f"source='{self.source}', "
            f"result={self.result}"
        )


class DataModel(Base):
    __tablename__ = "wis_data_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_view_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wis_table_view.id", ondelete="SET NULL"),
        nullable=False,
    )
