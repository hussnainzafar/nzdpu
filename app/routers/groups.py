"""Groups router"""

import json
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette import status

from app.db.models import AuthRole, Group, user_group
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas import group as group_schema

from .utils import (
    check_admin_access_rights,
    load_group,
    load_user,
    update_user_data_last_accessed,
)


class GroupError(str, Enum):
    """
    Group errors
    """

    USER_ALREADY_BELONGS_TO_GROUP = "The user already belongs to this group."
    INVALID_USER_GROUP_COMBINATION = "Invalid user and group combination."


# creates the router
router = APIRouter(
    prefix="/groups",
    tags=["groups"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[group_schema.GroupGet])
async def list_groups(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Return the list of all groups

    Parameters
    ----------
        filter_by - filter as dict e.g. {"name":"sample"}
        order_by - list of ordering fields e.g. ["name","id"]
        order - default "asc", can apply "asc" and "desc"

    Returns
    -------
        the list of groups
    """

    async with db_manager.get_session() as _session:
        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
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
        # load groups
        query = select(Group)
        # apply filtering from filter_by query params
        if "name" in filter_dict:
            query = query.where(Group.name.ilike(f"%{filter_dict['name']}%"))

        # order by query parameter
        for field in order_by_list:
            if field == "name":
                query = query.order_by(
                    Group.name.asc() if order == "asc" else Group.name.desc()
                )
            elif field == "id":
                query = query.order_by(
                    Group.id.asc() if order == "asc" else Group.id.desc()
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}. Must be name or id"
                    ),
                )
        result = await _session.execute(query)
    return result.scalars().unique().all()


@router.get("/{group_id}", response_model=group_schema.GroupGet)
async def get_group(
    group_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Return the details of a group

    Parameters
    ----------
        group_id - group identifier
    Returns
    -------
        group data
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

        return await load_group(group_id, _session)


@router.post("", response_model=group_schema.GroupGet)
async def create_group(
    group: group_schema.GroupCreate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Creates a new group

    Parameters
    ----------
        group - group input data
    Returns
    -------
        the new group
    """

    new_group = Group(**group.model_dump())
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        _session.add(new_group)
        await _session.commit()

    return new_group


@router.patch("/{group_id}", response_model=group_schema.GroupGet)
async def update_group(
    group_id: int,
    group_data: group_schema.GroupUpdate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Update an existing group

    Parameters
    ----------
        group_id - identifier of the group we want to update
        group_data - group input data
    Returns
    -------
        the updated group
    """
    # load group
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        db_group = await load_group(group_id, _session)
        # update attributes sent by the client
        group_update = group_data.model_dump(exclude_unset=True)
        for key, value in group_update.items():
            setattr(db_group, key, value)
        # save updated group
        _session.add(db_group)
        await _session.commit()

    return db_group


@router.post(
    "/{group_id}/add-user", response_model=group_schema.UserGroupResponse
)
async def add_user_to_group(
    group_id: int,
    user_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Add user to specific group

    Parameters
    ----------
        group_id - The ID of the group to which the user will be added
        user_id - The ID of the user to be inserted into the group
    Returns
    -------
        success (bool) - True if the user was successfully inserted into the group
    Raises
    ------
        HTTPException - If user already belongs to group
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

        await load_group(group_id, _session)
        await load_user(user_id, _session)

        # Create a new entry in the user_group table
        try:
            await _session.execute(
                user_group.insert().values(user_id=user_id, group_id=group_id)
            )
            await _session.commit()
            return group_schema.UserGroupResponse(success=True)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"user_id": GroupError.USER_ALREADY_BELONGS_TO_GROUP},
            ) from exc


@router.post(
    "/{group_id}/remove-user", response_model=group_schema.UserGroupResponse
)
async def remove_user_from_group(
    group_id: int,
    user_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Update an existing group

    Parameters
    ----------
        group_id - The ID of the group from which the user will be removed
        user_id - The ID of the user to be removed from the group
    Returns
    -------
         success (bool) - True if the user was successfully inserted into the group
    Raises
    ------
        HTTPException - If user and group combination does not exist in the table
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

        await load_group(group_id, _session)
        await load_user(user_id, _session)

        # Delete the entry from the user_group table
        result = await _session.execute(
            user_group.delete().where(
                user_group.c.user_id == user_id,
                user_group.c.group_id == group_id,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "user_id": GroupError.INVALID_USER_GROUP_COMBINATION,
                    "group_id": GroupError.INVALID_USER_GROUP_COMBINATION,
                },
            )

        await _session.commit()
    return group_schema.UserGroupResponse(success=True)
