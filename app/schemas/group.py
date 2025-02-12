"""Group schemas"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class GroupBase(BaseModel):
    """
    Base schema for Group
    """

    name: str
    description: Optional[str] = Field(default="")
    delegate_user_id: Optional[int] = None
    delegate_group_id: Optional[int] = None


class GroupCreate(GroupBase):
    """
    Create schema for Group
    """


class GroupGet(GroupBase):
    """
    Group schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class GroupUpdate(BaseModel):
    """
    Update schema for Group view
    """

    name: Optional[str] = None
    description: Optional[str] = Field(default="")
    delegate_user_id: Optional[int] = None
    delegate_group_id: Optional[int] = None


class UserGroupResponse(BaseModel):
    """
    User group response
    """

    success: bool
