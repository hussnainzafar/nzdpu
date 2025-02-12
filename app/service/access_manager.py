"""Access Manager"""

from enum import Enum
from typing import Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuthRole,
    ColumnView,
    Permission,
    SubmissionObj,
    TableView,
    User,
)


class AccessType(str, Enum):
    """
    Access types
    """

    LIST = "list"
    READ = "read"
    WRITE = "write"


class AccessManager:
    """
    Provides functions for access control on form elements
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize this instance
        Parameters
        ----------
        session - database session
        """

        self.session = session

    @staticmethod
    def is_admin(user: User) -> bool:
        """
        Check if user is an administrator
        Parameters
        ----------
        user - user to check

        Returns
        -------
        True if user owns an administrative role, False otherwise
        """

        user_groups: list[str] = (
            [group.name for group in user.groups] if user.groups else []
        )

        return AuthRole.ADMIN in user_groups

    @staticmethod
    def access_type_granted(access_type: AccessType, permission: Permission):
        """
        Check if an access type is granted by a permissions
        Parameters
        ----------
        access_type - access type to verify
        permission - permissions to check against

        Returns
        -------
        True if the permission grants access of this type, False otherwise
        """

        granted: bool = False

        if access_type == AccessType.READ:
            granted = permission.read
        elif access_type == AccessType.WRITE:
            granted = permission.write
        elif access_type == AccessType.LIST:
            granted = permission.list

        return granted

    def user_granted(
        self, access_type: AccessType, user: User, permissions
    ) -> bool:
        """
        Check if a set of permissions grant user a specific access type
        Parameters
        ----------
        access_type - type of access we want to verify
        user - user we want to check grants of
        permissions - permissions set to look into

        Returns
        -------
        True if user is granted the specified access type, False otherwise
        """

        granted: bool = False

        user_groups: list[int] = [group.id for group in user.groups]
        for permission in permissions:
            # check if permission grants access type
            if self.access_type_granted(access_type, permission):
                user_id = int(permission.user_id) if permission.user_id else 0
                group_id = (
                    int(permission.group_id) if permission.group_id else 0
                )
                if user_id > 0 and user_id == user.id:
                    # user granted
                    granted = True
                    break

                if group_id > 0 and group_id in user_groups:
                    # user group granted
                    granted = True
                    break

        return granted

    async def can_read_write(
        self,
        entity: Union[TableView, ColumnView, SubmissionObj],
        user: User,
        access_type: AccessType,
    ) -> bool:
        """
        Check if user has read / write access to an entity in the model.
        Parameters
        ----------
        entity - entity we want to check permissions on. Must be one of: "table view", "attribute view", "submission".
        user - user to check permissions of
        Returns
        -------
        True if user has read / write access to the entity, False otherwise
        """

        can_read_write: bool = AccessManager.is_admin(user)

        if not can_read_write:
            # get permissions set
            set_id: int = (
                int(entity.permissions_set_id)
                if entity.permissions_set_id
                else 0
            )

            if set_id == 0 and isinstance(entity, ColumnView):
                # check parent view
                set_id = (
                    int(entity.table_view.permissions_set_id)
                    if entity.table_view.permissions_set_id
                    else 0
                )

            if set_id > 0:
                # load permissions
                result = await self.session.execute(
                    select(Permission).where(Permission.set_id == set_id)
                )
                permissions = result.scalars().unique().all()

                # check permissions for user
                can_read_write = False
                if access_type == AccessType.READ:
                    can_read_write = self.user_granted(
                        access_type=AccessType.READ,
                        user=user,
                        permissions=permissions,
                    )
                elif access_type == AccessType.WRITE:
                    can_read_write = self.user_granted(
                        access_type=AccessType.WRITE,
                        user=user,
                        permissions=permissions,
                    )

        return can_read_write

    async def can_list(
        self,
        entities,
        user: User | None = None,
    ):
        """
        Check if user has list access to an entity in the model.
        Parameters
        ----------
        entities - entity we want to check permissions on. Must be one of: "table view", "attribute view", "submission".
        user - user to check permissions of
        Returns
        -------
        True if user is admin ccess to the entity, False otherwise
        List of entities ids, empty list otherwise
        """
        can_list = False

        if user:
            can_list: bool = AccessManager.is_admin(user)
        entities_ids_list = []
        if not can_list:
            for entity in entities:
                # get permissions set
                set_id: int = (
                    int(entity.permissions_set_id)
                    if entity.permissions_set_id
                    else 0
                )
                if set_id > 0:
                    # load permissions
                    result = await self.session.execute(
                        select(Permission).where(Permission.set_id == set_id)
                    )
                    permissions = result.scalars().unique().all()
                    # check permissions for user
                    user_granted = False
                    if user:
                        user_granted = self.user_granted(
                            access_type=AccessType.LIST,
                            user=user,
                            permissions=permissions,
                        )
                    if user_granted:
                        entities_ids_list.append(entity.id)
        return can_list, entities_ids_list
