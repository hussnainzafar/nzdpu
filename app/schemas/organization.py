"""Organization schema"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# pylint: disable = too-few-public-methods


class OrganizationBase(BaseModel):
    """
    Base schema for organization
    """

    id: int
    lei: str
    legal_name: str
    nz_id: int
    jurisdiction: Optional[str] = Field(default="")
    sics_sector: Optional[str] = Field(default="")
    company_type: Optional[str] = Field(default="")
    company_website: Optional[str] = Field(default="")
    headquarter_address_lines: Optional[str] = Field(default="")
    headquarter_address_number: Optional[str] = Field(default="")
    headquarter_city: Optional[str] = Field(default="")
    headquarter_country: Optional[str] = Field(default="")
    headquarter_language: Optional[str] = Field(default="")
    headquarter_postal_code: Optional[str] = Field(default="")
    headquarter_region: Optional[str] = Field(default="")
    legal_address_lines: Optional[str] = Field(default="")
    legal_address_number: Optional[str] = Field(default="")
    legal_city: Optional[str] = Field(default="")
    legal_country: Optional[str] = Field(default="")
    legal_language: Optional[str] = Field(default="")
    legal_postal_code: Optional[str] = Field(default="")
    legal_region: Optional[str] = Field(default="")
    sics_sub_sector: Optional[str] = Field(default="")
    sics_industry: Optional[str] = Field(default="")


class OrganizationCreate(OrganizationBase):
    """
    Create schema for organization
    """


class OrganizationGet(OrganizationBase):
    """
    Get schema for organization
    """

    created_on: datetime
    last_updated_on: datetime
    active: bool = Field(default=True)
    model_config = ConfigDict(from_attributes=True)


class OrganizationGetWithNonLeiIdentifiers(OrganizationGet):
    """
    Get schema for organization with non lei identifiers
    """

    isics: Optional[str] = Field(default="")
    duns: Optional[str] = Field(default="")
    gleif: Optional[str] = Field(default="")
    sing_id: Optional[str] = Field(default="")


class OrganizationList(BaseModel):
    """
    Schema for list of organizations
    """

    start: int
    size: int
    items: List[OrganizationGet]


class OrganizationUpdate(BaseModel):
    """
    Update schema for organization
    """

    company_type: Optional[str] = None
    company_website: Optional[str] = None


class GetOrganizationByLEIResponse(OrganizationGet):
    """
    Schema for Get Organization by LEI Response
    """
