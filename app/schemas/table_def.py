"""Table definition schemas"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .column_def import ColumnDefSchemaAdd, ColumnDefSchemaUpdate

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class TableDefBase(BaseModel):
    """
    Base schema for table definition
    """

    name: str
    description: str | None = ""
    created_on: datetime | None = datetime.now()
    user_id: int | None = None
    heritable: bool | None = False


class TableDefCreate(TableDefBase):
    """
    Create schema for table definition
    """


class TableDefGet(TableDefBase):
    """
    Table definition schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class TableDefUpdate(BaseModel):
    """
    Update schema for table definition
    """

    description: str | None = None


class SchemaUpdatePayload(BaseModel):
    """
    Schema for schema update payload.
    """

    add_attributes: list[ColumnDefSchemaAdd] = []
    update_attributes: list[ColumnDefSchemaUpdate] = []


class SchemaUpdateResponse(BaseModel):
    """
    Schema for schema update response.
    """

    added: int
    updated: int


class GetSchemaID(BaseModel):
    """
    Schema for schema id response.
    """

    id: int
