"""Managed File schemas"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class FileBase(BaseModel):
    """
    Base schema for File Registry
    """

    value_id: Optional[int] = None
    vault_id: Optional[int] = None
    vault_obj_id: Optional[str] = ""
    view_id: int
    file_size: Optional[int] = None
    vault_path: str = ""
    checksum: Optional[str] = ""


class FileCreate(FileBase):
    """
    Create schema for File Registry
    """

    base64: str


class FileGet(FileBase):
    """
    File Registry schema
    """

    # fileDict: Dict[str] = Field(created_on={
    #     "value_constraint": {
    #         "set": {
    #             "min": 2015,
    #             "max": 100,
    #             "format": "^\w+$",
    #             "format": "%d/%m/%y%H:%M:%S",
    #             "accept": [{
    #                 "extension": "pdf",
    #                 "mime_type": "application/pdf"
    #             }]
    #         }
    #     }
    # }
    #  )
    created_on: Optional[datetime] = datetime.now()
    file_size: Optional[int] = None
    checksum: Optional[str] = ""
    id: int
    model_config = ConfigDict(from_attributes=True)


class FileGetResponse(FileGet):
    """
    Response Schema for FileGet
    """

    signed_url: str  # this is a temporary change
