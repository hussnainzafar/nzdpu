"""Get full schema"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.choice import ChoiceGet
from app.schemas.column_def import ColumnDefBase
from app.schemas.column_view import ColumnViewBase
from app.schemas.prompt import AttributePromptGet
from app.schemas.table_def import TableDefBase
from app.schemas.table_view import TableViewBase

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class GetAttributeView(ColumnViewBase):
    """
    Attribute view component of GetForm schema
    """

    id: int
    constraint_view: Optional[dict] = None
    choices: list[Optional[ChoiceGet]] = Field(default=[])


class GetAttribute(ColumnDefBase):
    """
    Attribute component of GetForm schema
    """

    id: int
    choices: list[ChoiceGet] | None = None
    prompts: list[AttributePromptGet] | None = None
    form: Optional[GetForm] = None
    views: list[GetAttributeView] | None = None


class GetFormView(TableViewBase):
    """
    Form view component of GetForm schema
    """

    id: int


class GetForm(TableDefBase):
    """
    Schema used for getting the full details of a form in a single operation
    """

    id: int
    views: list[GetFormView] = Field(default=[])
    attributes: list[GetAttribute] = Field(default=[])


GetAttribute.model_rebuild()
