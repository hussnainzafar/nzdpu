"""Table view schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.schemas.choice import ChoiceGet
from app.schemas.column_def import ColumnDefBase
from app.schemas.column_view import ColumnViewBase
from app.schemas.prompt import AttributePromptGet
from app.schemas.table_def import TableDefBase, TableDefGet

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class TableViewBase(BaseModel):
    """
    Base schema for table view
    """

    table_def_id: int
    name: str
    created_on: Optional[datetime | str] = None
    user_id: Optional[int] = None
    revision_id: Optional[int] = None
    description: str = Field(default="")
    revision: int = Field(default=1)
    active: bool = Field(default=False)
    constraint_view: Optional[dict | str] = None
    permissions_set_id: Optional[int] = None


class TableViewCreate(TableViewBase):
    """
    Create schema for table view
    """

    created_on: Annotated[
        Optional[datetime | str],
        BeforeValidator(
            lambda v: datetime.fromisoformat(v) if isinstance(v, str) else v
        ),
    ] = None


class TableViewGet(TableViewBase):
    """
    Table view schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class TableViewUpdate(BaseModel):
    """
    Update schema for table view
    """

    description: Optional[str] = None
    active: Optional[bool] = None
    permissions_set_id: Optional[int] = None


class FormViewGetFull(TableViewBase):
    """
    views component of the SubFormGetFull schema
    """

    id: int
    constraint_view: Optional[Any] = None


class FormGetFull(TableDefBase):
    """
    Form component of AttributeDefGetFull schema
    """

    id: int
    views: list[FormViewGetFull] | None = None
    attributes: list[AttributeDefGetFull] | None = None


class AttributeDefGetFull(ColumnDefBase):
    """
    Attribute definition component of the AttributeViewGetFull schema
    """

    id: int
    choices: list[ChoiceGet] | None = None
    prompts: list[AttributePromptGet] | None = None
    form: Optional[FormGetFull] = None
    model_config = ConfigDict(from_attributes=True)


class AttributeViewGetFull(ColumnViewBase):
    """
    Attribute view component of TableViewGetFull schema
    """

    id: int
    column_def: AttributeDefGetFull
    model_config = ConfigDict(from_attributes=True)


class TableViewGetFull(TableViewBase):
    """
    Schema used for getting the full details of a form-view in a single operation
    """

    id: int
    table_def: TableDefGet
    attribute_views: list[AttributeViewGetFull] | None = None
    model_config = ConfigDict(from_attributes=True)


FormGetFull.model_rebuild()


class TableViewRevisionUpdatePayload(BaseModel):
    """
    Table view schema for update revision request body.
    """

    add_attributes: list[int] | None = None
    remove_attributes: list[int] | None = None
    active: bool = False


class TableViewRevisionUpdateResponse(BaseModel):
    """
    Table view schema for update revision response.
    """

    added: int
    removed: int
    active: bool
