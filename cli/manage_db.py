"""CLI commands for database management"""

import asyncio
import json

import pandas as pd
import structlog
import typer
from alembic import config
from sqlalchemy import URL, MetaData, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tqdm import tqdm
from typing_extensions import Annotated

from app import settings
from app.db import models
from app.db.database import DBManager, leader_engine
from app.db.models import (
    AggregatedObjectView,
    AuthRole,
    Config,
    ConfigProperty,
    Group,
    Organization,
    OrganizationAlias,
    SubmissionObj,
    User,
    Vault,
)
from app.db.redis import RedisClient
from app.db.types import CompositeTypeInjector
from app.schemas.submission import SubmissionGet
from app.service.core.cache import CoreMemoryCache
from app.service.core.forms import FormValuesGetter
from app.service.core.loaders import FormBatchLoader
from app.utils import encrypt_password, get_engine_from_session
from cli.manage_forms import async_create

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# create CLI app
app = typer.Typer()


# ASYNC FUNCTIONS
async def async_delete_tracking_data():
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        deleted_users = (
            (
                await session.execute(
                    select(User).filter(User.deleted.is_(True))
                )
            )
            .scalars()
            .all()
        )
        print(f"Found {len(deleted_users)} deleted users.")
        for user in deleted_users:
            print(
                f"Deleting tracking data for user {user.email} for last 30 days."
            )
            await session.execute(
                text(
                    f"DELETE FROM wis_tracking WHERE user_email = '{user.email}' AND date_time > now() - interval '30 days'",
                )
            )
            print(f"Deleted tracking data for user {user.email}.")
        await session.commit()
        await session.close()


async def async_db_init_new_env(
    data_path: str,
    user_name: str,
    user_password: str,
    superuser: bool,
) -> None:
    """
    Asynchronous db_init when db_init called with new_env flag.
    """

    # create groups and vault
    await async_create_groups_and_vault()

    # create user
    await async_create_user(
        name=user_name, password=user_password, superuser=superuser
    )

    # seed initial data
    await async_create(path=data_path)


def get_init_config() -> list:
    """
    Return the initial application configuration parameters
    :return: list of configuration parameters
    """
    return [
        Config(
            name=ConfigProperty.GENERAL_SYSTEM_EMAIL_ADDRESS.value,
            type=Config.TYPE_STRING,
            value="",  # Default value as a string
            description="System email address.",
        ),
        Config(
            name=ConfigProperty.DATA_EXPLORER_DOWNLOAD_ALL.value,
            type=Config.TYPE_INTEGER,
            value="0",
            description="Control download all in Data Explorer (0 or 1).",
        ),
        Config(
            name=ConfigProperty.DATA_EXPLORER_DOWNLOAD_SAMPLE.value,
            type=Config.TYPE_INTEGER,
            value="1",
            description="Control download sample in Data Explorer (0 or 1).",
        ),
        Config(
            name=ConfigProperty.DATA_EXPLORER_DOWNLOAD_NONE.value,
            type=Config.TYPE_INTEGER,
            value="0",
            description="Control download none in Data Explorer (0 or 1).",
        ),
        Config(
            name=ConfigProperty.COMPANY_PROFILE_DOWNLOAD_ALL.value,
            type=Config.TYPE_INTEGER,
            value="0",
            description="Control download all in Company Profile (0 or 1).",
        ),
        Config(
            name=ConfigProperty.COMPANY_PROFILE_DOWNLOAD_NONE.value,
            type=Config.TYPE_INTEGER,
            value="0",
            description="Control download none in Company Profile (0 or 1).",
        ),
        Config(
            name=ConfigProperty.DATA_DOWNLOAD_SHOW_ALL.value,
            type=Config.TYPE_INTEGER,
            value="0",
            description="Show all data downloads (0 or 1).",
        ),
        Config(
            name=ConfigProperty.DATA_DOWNLOAD_EXCLUDE_CLASSIFICATION.value,
            type=Config.TYPE_INTEGER,
            value="1",
            description="Exclude classification in data downloads (0 or 1).",
        ),
        Config(
            name=ConfigProperty.SECURITY_ENABLE_CAPTCHA.value,
            type=Config.TYPE_BOOLEAN,
            value="True",
            description="Handle captcha for bots (True or False)",
        ),
    ]


async def async_create_groups_and_vault() -> None:
    """
    Asynchronous create_groups_and_vault.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # create default roles
        groups = [
            Group(name=AuthRole.ADMIN, description="Administrators"),
            Group(name=AuthRole.DATA_EXPLORER, description="Data explorers"),
            Group(name=AuthRole.DATA_PUBLISHER, description="Data publishers"),
            Group(name=AuthRole.SCHEMA_EDITOR, description="Schema editors"),
        ]
        # get existing groups
        existing_groups = (await session.scalars(select(Group))).unique().all()
        if not existing_groups:
            session.add_all(groups)
        else:
            for group in groups:
                if group.name not in [g.name for g in existing_groups]:
                    session.add(group)

        existing_vaults = (await session.scalars(select(Vault))).all()
        if not existing_vaults:
            # create default vault
            vault = Vault(
                name="Google Cloud Storage",
                storage_type=0,
                access_type="google_adc",
                access_data="",
            )

            session.add(vault)

        await session.commit()


async def async_create_config_properties() -> None:
    """
    Asynchronous create_config_properties.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        existing_config_properties = (
            await session.scalars(select(Config))
        ).all()
        if not existing_config_properties:
            # Populate the wis_config table with initial configuration settings
            init_config = get_init_config()
            for config_entry in init_config:
                config_model = Config(
                    name=config_entry.name,
                    type=config_entry.type,
                    value=config_entry.value,
                    description=config_entry.description,
                )
                session.add(config_model)

            await session.commit()


async def async_create_all() -> None:
    """
    Asynchronous create_all.
    """
    # we dont need to create tables here as alembic has already done that
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        try:
            async with CompositeTypeInjector.from_session(session) as injector:
                await injector.create_composite_types_in_postgres()
        except Exception as e:
            raise e

    await async_create_groups_and_vault()
    await async_create_config_properties()


async def async_drop_all() -> None:
    """
    Asynchronous drop_all.
    """

    metadata = MetaData()

    async with leader_engine.begin() as conn:
        await conn.execute(text("DROP EXTENSION IF EXISTS pg_trgm;"))
        await conn.execute(text("DROP EXTENSION IF EXISTS fuzzystrmatch;"))
        await conn.execute(text("DROP EXTENSION IF EXISTS unaccent;"))
        await conn.run_sync(metadata.reflect)
        # Drop all tables
        await conn.run_sync(metadata.drop_all)
        # Drop all sequences because some remained there because of applied migration
        await conn.execute(
            text(
                "DO $$ DECLARE r RECORD; BEGIN FOR r IN (SELECT relname FROM pg_class where relkind = 'S') LOOP EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(r.relname) || ' CASCADE'; END LOOP; END $$;"
            )
        )

    print("Database dropped!")


async def async_create_role(name: str, description: str = "") -> None:
    """
    Asynchronous create_role.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # check if group exists
        group = await session.scalar(select(Group).filter_by(name=name))
        if not group:
            # create group
            group = Group(name=name, description=description)
            session.add(group)
            await session.commit()


async def async_delete_role(name: str) -> None:
    """
    Asynchronous delete_role.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # load group
        group = await session.scalar(select(Group).filter_by(name=name))
        if group:
            # delete group
            await session.delete(group)
            await session.commit()


async def async_create_users():
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        with open("cli/users.json") as f:
            users_data = f.read()
            data_json = json.loads(users_data)
            for json_user in data_json.get("users"):
                # encrypt password
                encrypted_pwd = encrypt_password(json_user.get("password"))
                org = await session.scalar(select(Organization))
                user_name = json_user.get("name").lower()
                # create user
                user = User(
                    name=user_name,
                    password=encrypted_pwd,
                    external_user_id=None,
                    organization_id=org.id,
                )
                session.add(user)
                await session.flush()
                # reload user with groups
                user = await session.scalar(
                    select(User)
                    .filter_by(name=user_name)
                    .options(selectinload(User.groups))
                )
                assert user
                # check if role specified for user
                group: Group | None = None
                group = await session.scalar(
                    select(Group).filter_by(name=json_user.get("role"))
                )
                if group:
                    # assign role to user
                    user.groups.append(group)
                # commit the transaction
                await session.commit()


async def async_create_user(
    name: str,
    password: str,
    superuser: bool,
    role: AuthRole | None = None,
) -> None:
    """
    Asynchronous create_user.
    """

    # create database session
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # check if user exists
        user = await session.scalar(
            select(User)
            .filter_by(name=name)
            .options(selectinload(User.groups))
        )
        if not user:
            # organization = await session.scalar(select(Organization))
            # if not organization:
            #     organization = Organization(
            #         lei="000012345678",
            #         legal_name="testorg",
            #         jurisdiction="US-MA",
            #         sics_sector=SICSSectorEnum.INFRASTRUCTURE,
            #         sics_sub_sector="subsector",
            #         sics_industry="sics_industry",
            #     )
            #     session.add(organization)
            #     await session.commit()

            # encrypt password
            encrypted_pwd = encrypt_password(password)
            # create user
            user = User(
                name=name,
                password=encrypted_pwd,
                external_user_id=None,
                # organization_id=organization.id,
            )
            session.add(user)
            await session.flush()
            # reload user with groups
            user = await session.scalar(
                select(User)
                .filter_by(name=name)
                .options(selectinload(User.groups))
            )
            assert user

            # check if role specified for user
            group: Group | None = None
            if superuser:
                role = AuthRole.ADMIN
            if role:
                # load role
                group = await session.scalar(
                    select(Group).filter_by(name=role)
                )

            if group:
                # assign role to user
                user.groups.append(group)

            # commit the transaction
            await session.commit()
        else:
            raise ValueError("User already exists.")


async def async_delete_user(name: str) -> None:
    """
    Asynchronous delete_user.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # load user
        user = await session.scalar(select(User).filter_by(name=name))
        if user:
            # delete user
            await session.delete(user)
            await session.commit()


async def async_add_role(role: str, username: str) -> None:
    """
    Asynchronous add_role.
    """

    # create database session
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # load user and group
        user = await session.scalar(
            select(User)
            .filter_by(name=username)
            .options(selectinload(User.groups))
        )
        group = await session.scalar(select(Group).filter_by(name=role))
        if user and group:
            # check if user already belongs to group
            group_names = [group.name for group in user.groups]
            if group.name not in group_names:
                # add user to group
                user.groups.append(group)
                await session.commit()
        else:
            print(
                f"Failed to add '{role}' to '{username}':"
                " user or role not found!"
            )


async def async_remove_role(role: str, username: str) -> None:
    """
    Asynchronous remove_role.
    """

    # create database session
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # load user
        user = await session.scalar(
            select(User)
            .filter_by(name=username)
            .options(selectinload(User.groups))
        )

        if user:
            # check if user is already in group
            group_names = [group.name for group in user.groups]
            if role in group_names:
                # load group
                group = await session.scalar(
                    select(Group).filter_by(name=role)
                )
                assert group
                # remove user from group
                user.groups.remove(group)
                await session.commit()


async def async_create_aggregated_forms():
    db_manager = DBManager()

    async with db_manager.get_session() as session:
        try:
            statement = select(AggregatedObjectView).limit(1)
            await session.execute(statement)
        except SQLAlchemyError as e:
            print("AggregateObjectView table does not exist. Creating...")
            await session.rollback()
            print(e)
            tables = [AggregatedObjectView.__table__]
            engine = get_engine_from_session(session)
            async with engine.begin() as conn:
                # create database tables
                await conn.run_sync(models.Base.metadata.create_all, tables)
                print("Created AggregateObjectView table")

        static_cache = CoreMemoryCache(session)
        redis_cache = RedisClient(
            host=settings.cache.host,
            port=settings.cache.port,
            password=settings.cache.password,
        )
        await static_cache.load_data()
        result = await session.scalars(select(SubmissionObj))
        submissions = result.all()
        if not submissions:
            print("No submissions found.")
            return

        print(
            "Loading aggregates for {} submissions...".format(len(submissions))
        )
        for submission_obj in tqdm(
            submissions, mininterval=6, unit="submission", colour="#11d3fa"
        ):
            existing_aggregate = select(AggregatedObjectView).filter(
                AggregatedObjectView.obj_id == submission_obj.id
            )
            existing_aggregate_value = (
                await session.execute(existing_aggregate)
            ).first()
            if existing_aggregate_value:
                continue

            submission_obj.values = {}
            submission = SubmissionGet.model_validate(submission_obj)
            form_loader = FormBatchLoader(
                session, static_cache, redis_cache, submission.id
            )
            form_data = await form_loader.fetch_form_row_data()
            primary_table_def = form_loader.primary_form_table_def
            form_manager = FormValuesGetter(
                static_cache,
                redis_cache,
                form_rows=form_data,
                primary_form=primary_table_def,
            )
            (
                submission_values,
                submission_units,
            ) = await form_manager.get_values()
            submission.values = submission_values[0]
            submission.units = submission_units[0]
            new_aggregate = AggregatedObjectView(
                obj_id=submission.id,
                data=submission.model_dump_json(),
            )
            session.add(new_aggregate)
        await session.commit()
        print("Aggregates are loaded.")


async def get_nz_id_by_legal_name(
    session: AsyncSession, legal_name: str, lei: str | None = None
) -> int | None:
    stmt = select(Organization.nz_id).where(
        or_(
            Organization.legal_name == legal_name,
            (Organization.lei == lei) if lei else False,
        )
    )
    result_query = await session.execute(stmt)
    return result_query.scalar_one_or_none()


async def async_create_organization_alias():
    db_manager = DBManager()
    file_path = "tests/data/company_alias_list.xlsx"
    df = pd.read_excel(file_path)

    if (
        "LEGAL_NAME" not in df.columns
        or "ALIAS" not in df.columns
        or "LEI" not in df.columns
    ):
        raise ValueError(
            "Excel file must contain 'LEGAL_NAME', 'ALIAS', and 'LEI' columns."
        )

    legal_name_to_nz_id_dict: dict[str, int] = {}

    async with db_manager.get_session() as session:
        for _, row in df.iterrows():
            legal_name = row["LEGAL_NAME"]
            alias = row["ALIAS"] if not pd.isna(row["ALIAS"]) else ""
            lei = row["LEI"] if not pd.isna(row["LEI"]) else None
            nz_id = legal_name_to_nz_id_dict.get("legal_name")
            # if we did not fetch already nz_id, fetch it
            if nz_id is None:
                nz_id = await get_nz_id_by_legal_name(session, legal_name, lei)
                legal_name_to_nz_id_dict[legal_name] = nz_id

            if alias == "":
                print(
                    f"Alias is empty for organization '{legal_name}', skip alias add."
                )
                continue

            if nz_id is None:
                print(
                    f"Organization '{legal_name}' or LEI '{lei}' does not exist in database, skipping alias addition."
                )
                continue

            organization_alias = OrganizationAlias(
                nz_id=nz_id,
                alias=alias.strip(),
            )

            session.add(organization_alias)

        await session.commit()

    print(f"Successfully added aliases from {file_path} to the database.")


# SYNC COMMANDS


@app.command()
def db_init(
    data_path: str = typer.Argument(None),
    user_name: str = typer.Argument(None),
    user_password: str = typer.Argument(None),
    uri: str = typer.Argument(None),
    superuser: bool = typer.Argument(True),
    new_env: Annotated[bool, typer.Option("-y")] = False,
) -> None:
    """
    Create database tables with alembic
    """

    if not new_env:
        confirm = input("Does this migration apply to new environment? (y/N) ")
        if confirm:
            new_env = confirm.upper() == "Y"

    # create database tables using alembic
    alembic_cfg = config.Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "app:alembic:alembic")
    if not uri:
        settings_uri = settings.LIVE_DATABASE_LEADER_URI
        if isinstance(settings_uri, URL):
            uri = settings_uri.render_as_string()
        else:
            uri = settings_uri
    alembic_cfg.set_main_option("sqlalchemy.url", uri)

    config.command.upgrade(alembic_cfg, "head")

    if new_env:
        asyncio.run(
            async_db_init_new_env(
                data_path=data_path,
                user_name=user_name,
                user_password=user_password,
                superuser=superuser,
            )
        )


@app.command()
def create_groups_and_vault() -> None:
    """
    Create groups
    """

    asyncio.run(async_create_groups_and_vault())


@app.command()
def create_all() -> None:
    """
    Create database tables
    """

    asyncio.run(async_create_all())


@app.command()
def create_aggregated_forms():
    asyncio.run(async_create_aggregated_forms())


@app.command()
def create_organizations_aliases():
    """
    Populate Organizations aliases from excel file
    """
    asyncio.run(async_create_organization_alias())


# pylint: disable = invalid-name
@app.command()
def drop_all(y: Annotated[bool, typer.Option("-y")] = False) -> None:
    """
    Delete all tables from database
    """

    if not y:
        confirm = input("Confirm dropping all tables from database? (y/N) ")
        if confirm:
            y = confirm.upper() == "Y"

    if y:
        asyncio.run(async_drop_all())


@app.command()
def create_role(
    name: str, description: Annotated[str, typer.Argument()] = ""
) -> None:
    """
    Create a new permissions group (role)
    """

    asyncio.run(async_create_role(name=name, description=description))


@app.command()
def delete_role(name: str) -> None:
    """
    Delete a permissions group (role)
    """

    confirm = input(f"Confirm deleting role '{name}'? (y/N) ")
    if confirm and confirm.upper() == "Y":
        asyncio.run(async_delete_role(name=name))


@app.command()
def create_user(
    name: str,
    password: str,
    superuser: bool = False,
    role: AuthRole = typer.Argument(None),
) -> None:
    """
    Create a new user
    """

    asyncio.run(
        async_create_user(
            name=name, password=password, superuser=superuser, role=role
        )
    )


@app.command()
def create_users() -> None:
    """
    Create a new users
    """
    asyncio.run(async_create_users())


@app.command()
def delete_user(name: str) -> None:
    """
    Delete a user
    """

    confirm = input(f"Confirm deleting user '{name}'? (y/N) ")
    if confirm and confirm.upper() == "Y":
        asyncio.run(async_delete_user(name=name))


@app.command()
def add_role(role: str, username: str) -> None:
    """
    Add role to user
    """

    asyncio.run(async_add_role(role=role, username=username))


@app.command()
def remove_role(role: str, username: str) -> None:
    """
    Remove role from user
    """

    asyncio.run(async_remove_role(role=role, username=username))


@app.command()
def delete_tracking_data() -> None:
    """delete-tracking-data"""
    asyncio.run(async_delete_tracking_data())


if __name__ == "__main__":
    # start CLI App
    app()
