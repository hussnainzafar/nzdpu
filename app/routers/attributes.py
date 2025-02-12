"""Attributes router."""

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import selectinload

from app.db.models import AuthRole, ColumnDef, TableDef
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas import column_def as column_def_schema

from .utils import (
    ErrorMessage,
    check_admin_access_rights,
    load_attribute,
    update_user_data_last_accessed,
)

# creates the router
router = APIRouter(
    prefix="/schema/attributes",
    tags=["attributes"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=column_def_schema.ColumnDefResponse)
async def list_attributes(
    db_manager: DbManager,
    start: Annotated[int | None, Query(gt=-1)] = 0,
    limit: Annotated[int | None, Query(gt=-1)] = 1000,
    order_by: Optional[str] = None,
    order: str = "asc",
    filter_by: Optional[str] = None,
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
    Return a paginated list of all attributes.

    Parameters
    ----------
    start : int, optional
        The starting index, by default 0
    limit : int, optional
        The number of items per page, by default 1000
    order_by : list of str, optional
        The fields to sort by, by default None
    order : str, optional
        The sort order, either 'asc' or 'desc', by default 'asc'
    filter_by : str, optional
        The filter criteria in JSON format, by default None

    Returns
    -------
    dict
        A dictionary containing the start index, end index, total count and the list of attributes.
    """
    # load attributes with pagination
    stmt = select(ColumnDef)

    if filter_by:
        filter_criteria = json.loads(filter_by)
        for key, value in filter_criteria.items():
            stmt = stmt.where(getattr(ColumnDef, key).contains(value))
    # Apply sorting
    if order_by:
        order_by = json.loads(order_by)
        for ob in order_by:
            if order.lower() == "desc":
                stmt = stmt.order_by(desc(ob))
            else:
                stmt = stmt.order_by(asc(ob))

    stmt = stmt.offset(start).limit(limit)

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        result = await _session.execute(stmt)
        items = result.scalars().all()

        # Get total number of records
        # pylint: disable=not-callable
        total_stmt = select(func.count()).select_from(ColumnDef)  # pylint: disable=not-callable
        total_result = await _session.execute(total_stmt)
        total = total_result.scalar_one()

    # Prepare response
    response = {
        "start": start,
        "end": start + len(items),
        "total": total,
        "items": items,
    }

    return response


@router.get("/{attribute_id}", response_model=column_def_schema.ColumnDefGet)
async def get_attribute(
    attribute_id: int,
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
    Return the details of an attribute

    Parameters
    ----------
        attribute_id - attribute identifier
    Returns
    -------
        attribute data
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        return await load_attribute(attribute_id, _session)


@router.post("", response_model=column_def_schema.ColumnDefGet)
async def create_attribute(
    attribute: column_def_schema.ColumnDefCreate,
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
    Creates a new attribute

    Parameters
    ----------
        attribute - attribute input data
    Returns
    -------
        the new attribute
    """

    if attribute.table_def_id is not None:
        # check provided table def exists
        table_def_id = attribute.table_def_id
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

            # check admin access rights
            await check_admin_access_rights(
                session=_session, current_user=current_user
            )

            result = await _session.execute(
                select(TableDef)
                .options(selectinload(TableDef.columns))
                .where(TableDef.id == table_def_id)
            )
        table_def: TableDef = result.scalars().first()
        if table_def is None:
            # return 404 on invalid (non-existing) table def ID
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "attribute.table_def_id": (
                        ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE
                    )
                },
            )

        # check there is no such attribute in the table already
        attr_names: list[str] = [attr.name for attr in table_def.columns]
        if attribute.name in attr_names:
            # duplicated attribute in table
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"attribute.name": ErrorMessage.DUPLICATED_ATTRIBUTE},
            )

    attribute_dict = attribute.model_dump()
    if (
        "user_id" not in attribute_dict
        or attribute_dict["user_id"] is None
        or attribute_dict["user_id"] == 0
    ):
        attribute.user_id = current_user.id

    # creates the attribute
    new_attribute = ColumnDef(**attribute.model_dump())
    async with db_manager.get_session() as _session:
        _session.add(new_attribute)
        await _session.commit()
    return new_attribute


@router.patch("/{attribute_id}", response_model=column_def_schema.ColumnDefGet)
async def update_attribute(
    attribute_id: int,
    attribute_data: column_def_schema.ColumnDefUpdate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.SCHEMA_EDITOR, AuthRole.ADMIN])
    ),
):
    """
    Update an existing attribute

    Parameters
    ----------
        attribute_id - identifier of the attribute we want to update
        attribute_data - attribute input data
    Returns
    -------
        the updated attribute
    """
    # load the existing attribute from the DB
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

    async with db_manager.get_session() as _session:
        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        db_attribute = await load_attribute(attribute_id, _session)
        # update the existing attribute
        attribute_update = attribute_data.model_dump(exclude_unset=True)
        for key, value in attribute_update.items():
            setattr(db_attribute, key, value)
        # save updated attribute
        _session.add(db_attribute)
        await _session.commit()
    return db_attribute
