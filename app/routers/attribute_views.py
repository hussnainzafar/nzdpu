"""Attribute view router"""

import datetime
import json
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthRole, ColumnView
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas.column_view import (
    ColumnViewCreate,
    ColumnViewGet,
    ColumnViewUpdate,
)
from app.service.access_manager import AccessManager, AccessType

from .utils import (
    check_access_rights,
    check_admin_access_rights,
    load_attribute_view,
    update_user_data_last_accessed,
)


class AttributeViewError(str, Enum):
    """
    Attribute view errors
    """

    ATTRIBUTE_VIEW_CANT_READ = "User not allowed to read this attribute view."
    ATTRIBUTE_VIEW_CANT_WRITE = (
        "User not allowed to write this attribute view."
    )


# creates the router
router = APIRouter(
    prefix="/schema/attribute-views",
    tags=["attribute-views"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[ColumnViewGet])
async def list_attribute_views(
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            required_roles=[
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        ),
    ),
    order_by: Optional[str] = None,
    order: str = "asc",
    filter_by: Optional[str] = None,
):
    """
    Return the list of attribute views

    Parameters
    ----------
    order_by : List[str], optional
        The fields to sort the results by, by default None
    order : str, optional
        The order direction. Can be “asc” or “desc”. Default: “asc”.
    filter_by : dict, optional
        A dictionary that contains (name, value) pairs of fields we want to filter the results on, by default None

    Returns
    -------
    list
        list of attribute views
    """

    # load attribute views
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # access manager
        access_manager = AccessManager(_session)
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        query = select(ColumnView)

        # Apply filters
        if filter_by:
            filter_criteria = json.loads(filter_by)
            for key, value in filter_criteria.items():
                query = query.where(getattr(ColumnView, key) == value)

        # Apply sorting
        if order_by:
            order_by = json.loads(order_by)
            for ob in order_by:
                if order.lower() == "desc":
                    query = query.order_by(desc(ob))
                else:
                    query = query.order_by(asc(ob))

        result = await _session.execute(query)
        if result:
            return result.scalars().all()

        # check list access rights
        is_admin, attribute_views_ids_list = await access_manager.can_list(
            entities=result.scalars().all(),
            user=current_user,
        )
        if not is_admin:
            result = await _session.execute(
                select(ColumnView).where(
                    ColumnView.id.in_(attribute_views_ids_list)
                )
            )
        else:
            result = await _session.execute(select(ColumnView))
    return result.scalars().all()


@router.get("/{attribute_view_id}", response_model=ColumnViewGet)
async def get_attribute_view(
    attribute_view_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            required_roles=[
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the details of an attribute view

    Parameters
    ----------
        attribute_view_id - attribute view identifier
    Returns
    -------
        attribute view data
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        attribute_view = await load_attribute_view(attribute_view_id, _session)

        # check read access rights
        await check_access_rights(
            session=_session,
            entity=attribute_view,
            user=current_user,
            access_type=AccessType.READ,
            error_message={
                "attribute_view_id": (
                    AttributeViewError.ATTRIBUTE_VIEW_CANT_READ
                )
            },
        )

    return attribute_view


@router.post("", response_model=ColumnViewGet)
async def create_attribute_view(
    attribute_view: ColumnViewCreate,
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
    Return the details of an attribute view

    Parameters
    ----------
        attribute_view - attribute view input data
    Returns
    -------
        the new attribute view
    """

    # "created_on" must be serialized for request then transformed to
    # datetime again

    attribute_view_dict = attribute_view.model_dump()

    if isinstance(attribute_view_dict["created_on"], datetime.datetime):
        # Set 'created_on' to the current date-time
        attribute_view.created_on = datetime.datetime.fromisoformat(
            attribute_view_dict["created_on"].strftime("%Y-%m-%dT%H:%M:%S")
        )
    elif isinstance(attribute_view_dict["created_on"], str):
        # If 'created_on' is provided, convert it from ISO format to datetime
        attribute_view.created_on = datetime.datetime.fromisoformat(
            attribute_view_dict["created_on"]
        )

    if (
        "user_id" not in attribute_view_dict
        or attribute_view.user_id is None
        or attribute_view.user_id == 0
    ):
        attribute_view.user_id = current_user.id
    db_attribute_view = ColumnView(**attribute_view.model_dump())
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=db_attribute_view,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={
                "attribute_view": AttributeViewError.ATTRIBUTE_VIEW_CANT_WRITE
            },
        )
        _session.add(db_attribute_view)
        await _session.commit()
    return db_attribute_view


@router.patch("/{attribute_view_id}", response_model=ColumnViewGet)
async def update_attribute_view(
    attribute_view_id: int,
    attribute_view_data: ColumnViewUpdate,
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
    Update an existing attribute view

    Parameters
    ----------
        attribute_view_id - identifier of the attribute view we want to update
        attribute_view_data - attribute view input data
    Returns
    -------
        the updated attribute view
    """

    # load attribute view
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        db_attribute_view = await load_attribute_view(
            attribute_view_id, _session
        )

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=db_attribute_view,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={
                "attribute_view_id": (
                    AttributeViewError.ATTRIBUTE_VIEW_CANT_WRITE
                )
            },
        )
        # update attributes sent by the client
        attribute_view_update = attribute_view_data.model_dump(
            exclude_unset=True
        )
        for key, value in attribute_view_update.items():
            setattr(db_attribute_view, key, value)
        # save updated attribute view
        _session.add(db_attribute_view)
        await _session.commit()
    return db_attribute_view
