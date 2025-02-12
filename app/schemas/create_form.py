"""Create form schemas"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.column_def import AttributeType
from app.schemas.constraint import Constraint

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class CreateFormView(BaseModel):
    """
    View component of CreateForm schema
    """

    name: str
    description: str = Field(default="")
    permissions_set_id: Optional[int] = None
    constraint_view: Any = None


class CreateChoice(BaseModel):
    """
    Choice component of CreateForm schema
    """

    set_name: str
    value: str
    description: str = Field(default="")
    choice_id: Optional[int] = None


class CreatePrompt(BaseModel):
    """
    Prompt component of CreateForm schema
    """

    value: str
    description: str = Field(default="")


class CreateAttributeView(BaseModel):
    """
    Attribute view component of CreateForm schema
    """

    constraint_value: list[Constraint] = Field(default=[])
    constraint_view: Optional[dict] = Field(default={})


class CreateAttribute(BaseModel):
    """
    Attribute component of CreateForm schema
    """

    name: str
    type: AttributeType
    view: Optional[CreateAttributeView] = None
    choices: list[CreateChoice] = []
    prompts: list[CreatePrompt] = []
    form: Optional[CreateForm] = None


class CreateForm(BaseModel):
    """
    Schema used for creating a complete form in a single operation
    """

    name: str
    description: str = Field(default="")
    user_id: Optional[int] = None
    view: Optional[CreateFormView] = None
    attributes: list[CreateAttribute] = Field(default=[])


CreateAttribute.model_rebuild()


class ViewRevisionCreate(BaseModel):
    """
    Response to a "create view revision" request
    """

    id: int
    name: str
    revision: int
