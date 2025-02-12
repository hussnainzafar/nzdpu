"""Utils module for router tests."""

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ColumnDef,
    ColumnView,
    Group,
    Permission,
    SubmissionObj,
    TableDef,
    TableView,
)
from app.forms.form_builder import FormBuilder
from app.schemas.column_def import ColumnDefCreate
from app.schemas.column_view import ColumnViewCreate
from app.schemas.create_form import CreateForm
from app.schemas.group import GroupCreate
from app.schemas.permission import PermissionCreate
from app.schemas.submission import SubmissionCreate
from app.schemas.table_def import TableDefCreate
from app.schemas.table_view import TableViewCreate

NZ_ID = 1000


async def create_test_attribute(
    session: AsyncSession,
    name: str = "test attribute",
    n: int | None = None,
):
    """
    Creates an attribute in the DB for testing purposes
    """
    column_name = name + str(n) if n is not None else name
    attribute_schema = ColumnDefCreate(
        name=column_name, table_def_id=1, attribute_type="text"
    )
    attribute = ColumnDef(**attribute_schema.dict())
    session.add(attribute)
    await session.commit()


async def create_test_form(
    path: str | Path, session: AsyncSession
) -> tuple[int, str, str | None]:
    """
    Creates a form for testing
    Parameters
    ----------
        path - path to the form specification
        session - database session
    Returns
    -------
        (ID, name, view_name) of the new form
    """

    # load form specification
    with open(path, encoding="utf-8") as f_spec:
        j_spec = json.load(f_spec)

    # validates and builds the schema
    form_spec = CreateForm(**j_spec)
    # builds the form
    builder = FormBuilder()
    form_id: int = await builder.go_build(spec=form_spec, session=session)

    return (
        form_id,
        form_spec.name,
        form_spec.view.name if form_spec.view else None,
    )


async def create_test_group(session: AsyncSession):
    """
    Creates a table definition in the DB for testing purposes
    """
    group_schema = GroupCreate(
        name="test_group",
        description="test_group_desc",
        delegate_user_id=1,
        delegate_group_id=1,
    )
    group = Group(**group_schema.dict())
    session.add(group)
    await session.commit()


async def create_test_permission(session: AsyncSession):
    """
    Creates a permission record in the DB for testing purposes
    """
    permission_schema = PermissionCreate(
        set_id=1,
        user_id=1,
        group_id=1,
        grant=True,
        list=True,
        read=True,
        write=False,
    )
    permission = Permission(**permission_schema.dict())
    session.add(permission)
    await session.commit()


async def create_test_table_def(session: AsyncSession):
    """
    Creates a table definition in the DB for testing purposes
    """
    test_schema = TableDefCreate(name="nzdpu_form")
    table_def = TableDef(**test_schema.dict())
    session.add(table_def)
    await session.commit()


async def create_test_table_view(
    session: AsyncSession,
    permissions_set_id: int = 0,
    name: str = "nzdpu_form_simple_test",
):
    """
    Creates a table view in the DB for testing purposes
    """

    table_view_schema = TableViewCreate(table_def_id=1, name=name, active=True)

    if permissions_set_id > 0:
        table_view_schema.permissions_set_id = permissions_set_id

    table_view = TableView(**table_view_schema.dict())
    session.add(table_view)
    await session.commit()


async def create_test_attribute_view(
    session: AsyncSession, permissions_set_id: int = 0
):
    """
    Creates an attribute view in the DB for testing purposes
    """
    attribute_view_schema = ColumnViewCreate(column_def_id=1, table_view_id=1)

    if permissions_set_id > 0:
        attribute_view_schema.permissions_set_id = permissions_set_id

    attribute_view = ColumnView(**attribute_view_schema.dict())
    session.add(attribute_view)
    await session.commit()


async def create_test_submission_with_empty_values(session: AsyncSession):
    """
    Creates a submission in the DB for testing purposes
    """
    submission_schema = SubmissionCreate(table_view_id=1, user_id=1, values={})
    submission_obj = SubmissionObj(
        **{"submitted_by": 1, **submission_schema.dict(exclude={"values"})}
    )
    submission_obj.name = "sample"
    session.add(submission_obj)
    await session.commit()
