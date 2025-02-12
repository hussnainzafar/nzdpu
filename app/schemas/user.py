"""User schemas"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
)

from app.db.models import AuthMode, AuthRole, UserPublisherStatusEnum

from . import group

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class UserBase(BaseModel):
    """
    Base schema for User
    """

    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    api_key: Optional[str] = None


class OrganizationTypes(str, Enum):
    FINANCIAL_INSTITUTION = "Financial Institution"
    NON_FINANCIAL_CORPORATE = "Non-Financial Corporate"
    ACADEMIA_EDUCATION_RESEARCH = "Academia / Education / Research"
    DATA_METHODOLOGY = "Data or Methodology Provider"
    GOVERNMENT_PUBLIC_SECTOR = "Government / Public Sector"
    INDUSTRY_TRADE = "Industry or Trade Association"
    NON_GOVERNMENTAL_ORGANIZATION = "Non-Governmental Organization"
    STANDARD_SETTER = "Standard Setter"
    OTHER = "Other"


class UserCreate(UserBase):
    """
    Create schema for User
    """

    email: EmailStr
    password: str
    hashed_password: str = Field(alias="password", default=None)
    groups: list[group.GroupBase] = []
    organization_type: Optional[OrganizationTypes] = None


class UserIdOnly(BaseModel):
    """
    User schema for returning ID only.
    """

    id: int
    verification_link: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class UserGet(UserBase, UserIdOnly):
    """
    User schema
    """

    email: Optional[str] = None
    enabled: bool = False
    created_on: datetime = datetime.now()
    last_access: Optional[datetime] = None
    external_user_id: Optional[str] = None
    data_last_accessed: Optional[datetime] = None
    organization_name: Optional[str] = None
    jurisdiction: Optional[str] = None
    groups: list[group.GroupGet]
    organization_type: Optional[OrganizationTypes] = None
    organization_id: Optional[int] = None
    lei: Optional[str] = None
    auth_mode: AuthMode = AuthMode.LOCAL


class PaginatedUserGet(BaseModel):
    """
    User schema
    """

    start: int
    end: int
    total: int
    items: List[UserGet]


class GroupFilter(str, Enum):
    ADMIN = AuthRole.ADMIN.value
    SCHEMA_EDITOR = AuthRole.SCHEMA_EDITOR.value
    DATA_EXPLORER = AuthRole.DATA_EXPLORER.value
    DATA_PUBLISHER = AuthRole.DATA_PUBLISHER.value


class UserLoginDataModel(BaseModel):
    """
    User login schema
    """

    username: str = Field(default="")
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """
    Update schema for User
    """

    name: Optional[str] = None
    email: Optional[EmailStr] = None
    enabled: Optional[bool] = None
    organization_name: Optional[str] = None
    organization_type: Optional[OrganizationTypes] = None
    jurisdiction: Optional[str] = None
    api_key: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[SecretStr] = None
    groups: list[group.GroupBase] | None = None


class UserApiCreateResponse(BaseModel):
    """
    Create API user response
    """

    id: int
    auth_mode: AuthMode
    external_user_id: str


class UserStandalone(UserIdOnly):
    """
    User schema for standalone api.
    """

    name: str
    first_name: str
    last_name: str
    enabled: bool


class UserPublisherRequest(BaseModel):
    """
    Schema for request payload in request-publisher-access endpoint
    """

    role: Optional[str] = None
    linkedin_link: Optional[AnyHttpUrl] = None
    company_lei: str
    company_type: Optional[str] = None
    company_website: Optional[AnyHttpUrl] = None


class UserPublisherResponse(BaseModel):
    """
    Schema for response in request-publisher-access.
    """

    status: UserPublisherStatusEnum


class UserApiKeyUpdate(BaseModel):
    """
    Update schema for User api_key
    """

    access_key: Optional[str] = None


class UserListResponse(BaseModel):
    items: List[UserGet]
    total: int


class UserDeleteResponse(BaseModel):
    """
    Schema for response after deleting a user
    """

    id: int
    deleted: bool


class UserUpdateResponse(UserGet):
    """
    Schema for reponse of update user API.
    """

    token: str
    refresh_token: Optional[str] = None
    recovery_link: Optional[str] = None
    verification_link: Optional[str] = None


class NotificationSignupResponse(BaseModel):
    """
    Response Schema for Notification Sign up API
    """

    user_id: int
    notifications: bool


class UserAdminGrant(BaseModel):
    """
    UserAdminGrant schema for update role
    """

    email: EmailStr


class UserAdminGrantResponse(BaseModel):
    """
    UserAdminGrant schema for update role response
    """

    user_id: list[int] = []
    role: Optional[str] = None


class AdminRevokeRequest(BaseModel):
    """
    AdminRevokeRequest schema for revoke
    """

    user_id: list[int] = []


class AdminRevokeResponse(BaseModel):
    """
    AdminRevokeResponse schema for revoke
    """

    success: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    """
    ApiKeyResponse schema for api key
    """

    api_key_success: str
