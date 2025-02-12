"""Tables router"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from starlette import status

from app.db.models import AuthRole, TableDef
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas.table_def import TableDefCreate, TableDefGet, TableDefUpdate

from .utils import (
    ErrorMessage,
    check_admin_access_rights,
    load_table_def,
    update_user_data_last_accessed,
)

# creates the router
router = APIRouter(
    prefix="/schema/tables",
    tags=["tables"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[TableDefGet])
async def list_tables(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the list of tables

    Parameters
    ----------
        filter_by - filter as dict e.g. {"name":"sample", "active":"true"}
        order_by - list of ordering fields e.g. ["name","id"]
        order - default "asc", can apply "asc" and "desc"

    Returns
    -------
        list of tables definition
    """

    # load table definitions
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # verify order parameter
        if order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid order value {order}. Must be 'asc' or 'desc'."
                ),
            )

        # parse the filter_by and order_by parameters
        filter_dict = {}
        order_by_list = []

        if filter_by:
            try:
                filter_dict = json.loads(filter_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid filter_by format. Must be a valid JSON"
                        " string."
                    ),
                ) from exc

        if order_by:
            try:
                order_by_list = json.loads(order_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid order_by format. Must be a valid JSON list of"
                        " strings."
                    ),
                ) from exc

        # load table def
        query = select(TableDef)

        # apply filtering from filter_by query params
        if "name" in filter_dict:
            query = query.where(
                TableDef.name.ilike(f"%{filter_dict['name']}%")
            )
        if "active" in filter_dict and filter_dict["active"].lower() == "true":
            pass
        elif (
            "active" in filter_dict
            and filter_dict["active"].lower() == "false"
        ):
            pass

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    TableDef.id.asc() if order == "asc" else TableDef.id.desc()
                )
            elif field == "name":
                query = query.order_by(
                    TableDef.name.asc()
                    if order == "asc"
                    else TableDef.name.desc()
                )
            elif field == "active":
                pass
            elif field == "created_on":
                query = query.order_by(
                    TableDef.created_on.asc()
                    if order == "asc"
                    else TableDef.created_on.desc()
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}."
                        " Must be id, name, active or created_on."
                    ),
                )

        result = await _session.execute(query)
    return result.scalars().all()


@router.get("/{table_id}", response_model=TableDefGet)
async def get_table(
    table_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the details of a table

    Parameters
    ----------
        table_id - table identifier
    Returns
    -------
        table data
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        return await load_table_def(table_id, _session)


@router.post("", response_model=TableDefGet)
async def create_table(
    table: TableDefCreate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the details of a table

    Parameters
    ----------
        table - table input data
    Returns
    -------
        the new table
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        # check there is no table with the same name already
        result = await _session.execute(
            select(TableDef).where(TableDef.name == table.name)
        )
        if result.first():
            # duplicated table
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"table": ErrorMessage.TABLE_DEF_EXISTS},
            )

        # create table
        table_dict = table.model_dump()
        if (
            "user_id" not in table_dict
            or table_dict["user_id"] is None
            or table_dict["user_id"] == 0
        ):
            table_dict["user_id"] = current_user.id
        db_table = TableDef(**table_dict)
        _session.add(db_table)
        await _session.commit()
    return db_table


@router.patch("/{table_id}", response_model=TableDefGet)
async def update_table(
    table_id: int,
    table_data: TableDefUpdate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Update an existing table

    Parameters
    ----------
        table_id - identifier of the table we want to update
        table_data - table input data
    Returns
    -------
        the updated table
    """

    # load table view
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_table = await load_table_def(table_id, _session)

    # update attributes sent by the client
    table_update = table_data.model_dump(exclude_unset=True)
    for key, value in table_update.items():
        setattr(db_table, key, value)
    # save updated table
    async with db_manager.get_session() as _session:
        _session.add(db_table)
        await _session.commit()
    return db_table
