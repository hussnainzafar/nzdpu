"""Attribute prompt schemas"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class AttributePromptBase(BaseModel):
    """
    Base schema for attribute prompt
    """

    column_def_id: int
    value: str
    description: Optional[str] = None
    language_code: Optional[str] = "en_US"
    role: str | None = None


class AttributePromptCreate(AttributePromptBase):
    """
    Create schema for attribute prompt
    """


class AttributePromptGet(AttributePromptBase):
    """
    Attribute prompt schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class PaginationResponse(BaseModel):
    """
    Pagination response schema
    """

    start: int
    end: int
    total: int
    items: List[AttributePromptGet]


class AttributePromptUpdate(BaseModel):
    """
    Update schema for attribute prompt
    """

    value: str | None = None
    description: str | None = None
    role: Optional[str] = None
    model_config = ConfigDict(extra="forbid")
