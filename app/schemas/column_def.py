"""Column definition schemas"""

from datetime import datetime
from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class AttributeType(StrEnum):
    """
    Supported attribute types
    """

    LABEL = "label"
    TEXT = "text"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    DATETIME = "datetime"
    SINGLE = "single"
    MULTIPLE = "multiple"
    FORM = "form"
    FILE = "file"
    INT_OR_NULL = "int_or_null"
    TEXT_OR_NULL = "text_or_null"
    FLOAT_OR_NULL = "float_or_null"
    FORM_OR_NULL = "form_or_null"
    BOOL_OR_NULL = "bool_or_null"
    FILE_OR_NULL = "file_or_null"


class ColumnDefBase(BaseModel):
    """
    Base schema for column definition
    """

    name: str
    attribute_type: AttributeType
    created_on: datetime = datetime.now()
    table_def_id: Optional[int] = None
    user_id: Optional[int] = None
    attribute_type_id: Optional[int] = None
    choice_set_id: Optional[int] = None


class ColumnDefCreate(ColumnDefBase):
    """
    Create schema for column definition
    """


class ColumnDefGet(ColumnDefBase):
    """
    Column definition schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class ColumnDefResponse(BaseModel):
    """
    Response schema for list_attributes endpoint
    """

    start: int = Field(..., description="The starting index")
    end: int = Field(..., description="The ending index")
    total: int = Field(..., description="Total number of records")
    items: List[ColumnDefGet] = Field(
        ..., description="The list of attributes"
    )


class ColumnDefSchemaAdd(BaseModel):
    """
    Schema for column definition addition in schema update endpoint.
    """

    name: str
    active: bool = False
    user_id: Optional[int] = None
    attribute_type: Optional[AttributeType] = None
    attribute_type_id: Optional[int] = None
    choice_set_id: Optional[int] = None


class ColumnDefUpdate(BaseModel):
    """
    Schema for column definition update in schema update endpoint.
    """

    name: Optional[str] = None
    table_def_id: Optional[int] = None
    user_id: Optional[int] = None
    attribute_type: Optional[AttributeType] = None
    attribute_type_id: Optional[int] = None
    choice_set_id: Optional[int] = None


class ColumnDefSchemaUpdate(ColumnDefUpdate):
    """
    Schema for column definition update in schema update endpoint.
    """

    id: int
