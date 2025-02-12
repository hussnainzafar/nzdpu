"""Data models."""

from datetime import datetime

from pydantic import BaseModel

from app.db.models import AuthMode, AuthRole
from app.schemas.enums import SICSSectorEnum, SubmissionObjStatusEnum


class WisAttributePromptDataModel(BaseModel):
    id: int
    column_def_id: int | None = None
    value: str
    description: str | None = None
    language_code: str | None = None
    role: str | None = None


class WisChoiceDataModel(BaseModel):
    id: int
    choice_id: int
    set_id: int
    set_name: str
    value: str
    description: str | None = None
    order: int | None = None
    language_code: str | None = None


class WisColumnDefDataModel(BaseModel):
    id: int
    name: str
    table_def_id: int | None = None
    created_on: datetime
    user_id: int | None = None
    attribute_type: str
    attribute_type_id: int | None = None
    choice_set_id: int | None = None


class WisColumnViewDataModel(BaseModel):
    id: int
    column_def_id: int | None = None
    table_view_id: int | None = None
    created_on: datetime
    user_id: int | None = None
    permissions_set_id: int | None = None
    constraint_value: list[dict] | None = None
    constraint_view: dict | None = None
    choice_set_id: int | None = None


class WisConfigDatamodel(BaseModel):
    id: int
    name: str
    type: str
    value: str | None = None
    description: str | None = None


class WisGroupDataModel(BaseModel):
    id: int
    name: AuthRole
    description: str | None = None
    delegate_user_id: int | None = None
    delegate_group_id: int | None = None


class WisObjDataModel(BaseModel):
    id: int
    table_view_id: int
    name: str
    created_on: datetime
    revision: int
    active: bool
    activated_on: datetime
    user_id: int | None = None
    checked_out: bool
    checked_out_on: datetime | None = None
    permissions_set_id: int | None = None
    submitted_by: int
    data_source: int | None = None
    status: SubmissionObjStatusEnum | None = None
    lei: str


class WisOrganizationDataModel(BaseModel):
    id: int
    created_on: datetime = datetime.now()
    last_updated_on: datetime = datetime.now()
    active: bool
    lei: str
    legal_name: str
    jurisdiction: str | None = None
    company_type: str | None = None
    company_website: str | None = None
    headquarter_address_lines: str | None = None
    headquarter_address_number: str | None = None
    headquarter_city: str | None = None
    headquarter_country: str | None = None
    headquarter_language: str | None = None
    headquarter_postal_code: str | None = None
    headquarter_region: str | None = None
    legal_address_lines: str | None = None
    legal_address_number: str | None = None
    legal_city: str | None = None
    legal_country: str | None = None
    legal_language: str | None = None
    legal_postal_code: str | None = None
    legal_region: str | None = None
    sics_sector: SICSSectorEnum | None = None
    sics_sub_sector: str | None = None
    sics_industry: str | None = None


class WisTableDefDataModel(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_on: datetime
    user_id: int | None = None
    heritable: bool


class WisTableViewDataModel(BaseModel):
    id: int
    table_def_id: int
    name: str
    description: str | None = None
    revision: int
    revision_id: int | None = None
    active: bool
    created_on: datetime
    user_id: int | None = None
    permissions_set_id: int | None = None
    constraint_view: dict | None = None


class WisUserDataModel(BaseModel):
    id: int
    name: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    api_key: str | None = None
    enabled: bool
    password: str | None = None
    created_on: datetime = datetime.now()
    last_access: datetime | None = None
    refresh_token_uid: str | None = None
    token_iat: datetime | None = None
    auth_mode: AuthMode
    external_user_id: int | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    organization_type: str | None = None
    jurisdiction: str | None = None
    data_last_accessed: datetime | None = None
    failed_login_attempts: int
    deleted: bool
    notifications: bool


class WisUserGroupDataModel(BaseModel):
    user_id: int | None = None
    group_id: int | None = None


class WisVaultDataModel(BaseModel):
    id: int
    name: str
    storage_type: int
    access_type: str
    access_data: dict | None = None
