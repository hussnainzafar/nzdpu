"""Permission schemas"""

from typing import Optional

from pydantic import BaseModel, ConfigDict

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class PermissionBase(BaseModel):
    """
    Base schema for Permission
    """

    set_id: Optional[int] = None
    grant: bool = True
    list: bool = True
    read: bool = True
    write: bool = True
    group_id: Optional[int] = None
    user_id: Optional[int] = None


class PermissionCreate(PermissionBase):
    """
    Create schema for Permission
    """


class PermissionGet(PermissionBase):
    """
    Permission schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class PermissionUpdate(BaseModel):
    """
    Update schema for Permission view
    """

    grant: Optional[bool] = None
    list: Optional[bool] = None
    read: Optional[bool] = None
    write: Optional[bool] = None


class PermissionSetCreate(PermissionCreate):
    """
    Schema of a permission for "create permission set"
    """


class PermissionSetCreateResponse(BaseModel):
    """
    Response to "create permission set"
    """

    set_id: int
