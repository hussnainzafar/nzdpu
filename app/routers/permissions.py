"""Permissions router."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.db.models import AuthRole, Permission
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas import permission as permission_schema

from .utils import (
    load_group,
    load_permission,
    load_user,
    update_user_data_last_accessed,
)

# creates the router
router = APIRouter(
    tags=["permissions"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


# pylint: disable = unsupported-binary-operation
@router.get("", response_model=list[permission_schema.PermissionGet])
async def list_permissions(
    db_manager: DbManager,
    set_id: int | None = None,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Return the list of all permissions.

    Parameters
    ----------
        set_id (optional) - the permissions set identifier

    Returns
    -------
        the list of permissions
    """

    # load permissions
    query = select(Permission)
    if set_id is not None:
        query = query.where(Permission.set_id == set_id)
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        result = await _session.execute(query)

    return result.scalars().unique().all()


@router.get("/{permission_id}", response_model=permission_schema.PermissionGet)
async def get_permission(
    permission_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Return the details of a permission

    Parameters
    ----------
        permission_id - permission identifier

    Returns
    -------
        permission data
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        return await load_permission(permission_id, _session)


@router.post("", response_model=permission_schema.PermissionGet)
async def create_permission(
    permission: permission_schema.PermissionCreate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Creates a new permission

    Parameters
    ----------
        permission - permission input data

    Returns
    -------
        the new permission
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check that user exists
        if permission.user_id:
            await load_user(user_id=permission.user_id, session=_session)
        # check that group exists
        if permission.group_id:
            await load_group(group_id=permission.group_id, session=_session)

        new_permission = Permission(**permission.model_dump())
        _session.add(new_permission)
        await _session.commit()

    return new_permission


@router.patch(
    "/{permission_id}", response_model=permission_schema.PermissionGet
)
async def update_permission(
    permission_id: int,
    permission_data: permission_schema.PermissionUpdate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Update an existing permission

    Parameters
    ----------
        permission_id - identifier of the permission we want to update
        permission_data - permission input data

    Returns
    -------
        the updated permission
    """
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_permission = await load_permission(permission_id, _session)
        # update the existing permission
        permission_update = permission_data.model_dump(exclude_unset=True)
        for key, value in permission_update.items():
            setattr(db_permission, key, value)
        # save updated permission
        _session.add(db_permission)
        await _session.commit()

    return db_permission


@router.post(
    "/set", response_model=permission_schema.PermissionSetCreateResponse
)
async def create_permission_set(
    permission_set: list[permission_schema.PermissionSetCreate],
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Creates a new permission

    Parameters
    ----------
        permission_set - input data for the new permission set

    Returns
    -------
        identifier of the new permission set
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # compute next set identifier
        # pylint: disable = not-callable
        result = await _session.execute(select(func.max(Permission.set_id)))
        row = result.scalars().first()
        max_set_id = row if row else 0
        set_id = max_set_id + 1

        for permission in permission_set:
            # check that user exists
            if permission.user_id:
                await load_user(user_id=permission.user_id, session=_session)
            # check that group exists
            if permission.group_id:
                await load_group(
                    group_id=permission.group_id, session=_session
                )

            # create permission
            db_permission = Permission(**permission.model_dump())
            db_permission.set_id = set_id
            _session.add(db_permission)

        # create the permissions set
        await _session.commit()

    return permission_schema.PermissionSetCreateResponse(set_id=set_id)
