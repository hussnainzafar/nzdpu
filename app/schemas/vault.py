"""Vault schemas"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class VaultBase(BaseModel):
    """
    Base schema for vault
    """

    id: int
    storage_type: int
    name: Optional[str] = Field(default="")
    access_type: Optional[str] = Field(default="google_adc")
    access_data: Optional[str] = Field(default="")


class VaultGet(VaultBase):
    """
    Vault schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class VaultCreate(VaultBase):
    """
    Create schema for Vault
    """

    id: int = Field(gt=0)
