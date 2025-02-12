"""Firebase REST API client models."""

from datetime import datetime
from enum import Enum

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field


class FirebaseRequestTypeEnum(str, Enum):
    PASSWORD_RESET = "PASSWORD_RESET"


class GetAccountInfoResponseElementModel(BaseModel):
    """
    Response model for a user of the `get-account-info` endpoint response.

    Description from Firebase doc:

    localId (str): The uid of the current user.
    email (str): The email of the account.
    emailVerified (bool): Whether or not the account's email has
        been verified.
    displayName (str): The display name for the account.
    providerUserInfo (list): List of all linked provider objects which
        contain "providerId" and "federatedId".
    photoUrl (str): The photo Url for the account.
    passwordHash (str): Hash version of password.
    passwordUpdatedAt (datetime): The timestamp, in milliseconds, that
        the account password was last changed.
    validSince (str): The timestamp, in seconds, which marks a
        boundary, before which Firebase ID token are considered revoked.
    disabled (bool): Whether the account is disabled or not.
    lastLoginAt (str): The timestamp, in milliseconds, that the
        account last logged in at.
    createdAt (str): The timestamp, in milliseconds, that the
        account was created at.
    customAuth (bool): Whether the account is authenticated by the
        developer.
    """

    local_id: str = Field(alias="localId")
    email: EmailStr
    email_verified: bool = Field(alias="emailVerified")
    display_name: str | None = Field(alias="displayName", default=None)
    provider_user_info: list = Field(alias="providerUserInfo")
    photo_url: AnyHttpUrl | None = None
    password_hash: str = Field(alias="passwordHash")
    password_updated_at: datetime = Field(alias="passwordUpdatedAt")
    valid_since: str = Field(alias="validSince")
    disabled: bool = False
    last_login_at: str = Field(alias="lastLoginAt")
    created_at: str = Field(alias="createdAt")
    custom_auth: bool | None = Field(alias="customAuth", default=None)


class GetAccountInfoResponseModel(BaseModel):
    """
    Response model for the `get-account-info` endpoint.

    Description from Firebase doc:

    users (list): The account associated with the given Firebase ID token.
    """

    kind: str
    users: list[GetAccountInfoResponseElementModel]


class SignInWithEmailPasswordResponseModel(BaseModel):
    """
    Response model for the `sign-in-email-password` endpoint.

    Description from Firebase doc:

    idToken (str): A Firebase Auth ID token for the authenticated user.
    email (str): The email for the authenticated user.
    refreshToken (str): A Firebase Auth refresh token for the
        authenticated user.
    expiresIn (str): The number of seconds in which the ID token expires.
    localId (str): The uid of the authenticated user.
    registered (bool): Whether the email is for an existing account.
    """

    id_token: str = Field(alias="idToken")
    email: EmailStr
    refresh_token: str = Field(alias="refreshToken")
    expires_in: str = Field(alias="expiresIn")
    local_id: str = Field(alias="localId")
    registered: bool


class SendEmailVerificationResponseModel(BaseModel):
    """
    Response model for the `sign-email-verification` endpoint.

    Description from Firebase doc:

    email (str): The email of the account.
    """

    email: EmailStr


class SendPasswordResetEmailResponseModel(BaseModel):
    """
    Response model for the `send-password-reset-email` endpoint.

    Description from Firebase doc:

    email (str): User's email address.
    """

    email: EmailStr


class VerifyPasswordResetResponseModel(BaseModel):
    """
    Response model for the `verify-password-reset-code` endpoint.

    Description from Firebase doc:

    email (str): User's email address.
    requestType (str): Type of the email action code. Should be
        "PASSWORD_RESET".
    """

    email: EmailStr
    request_type: FirebaseRequestTypeEnum = Field(alias="requestType")


class UpdateResponseModel(BaseModel):
    """
    Response model for all functions handled by the `update` endpoint.

    localId (str): The uid of the current user.
    email (string): The email of the account.
    displayName (string): The display name for the account.
    photoUrl (string): The photo Url for the account.
    passwordHash (string): The password hash.
    providerUserInfo (list): List of all linked provider objects which
        contain "providerId" and "federatedId".
    idToken (str): New Firebase Auth ID token for user.
    refreshToken (str): A Firebase Auth refresh token.
    emailVerified (boolean): Whether or not the account's email has been
        verified.
    expiresIn (str): The number of seconds in which the ID token expires.
    """

    email: EmailStr
    local_id: str | None = Field(alias="localId", default=None)
    email_verified: bool = Field(default=False, alias="emailVerified")
    display_name: str | None = Field(alias="displayName", default=None)
    provider_user_info: list = Field(default=[], alias="providerUserInfo")
    photo_url: AnyHttpUrl | None = None
    password_hash: str = Field(alias="passwordHash")
    id_token: str = Field(default="", alias="idToken")
    refresh_token: str | None = Field(alias="refreshToken", default=None)
    expires_in: str | None = Field(alias="expiresIn", default=None)


class GetIdOtkenFromRefreshTokenResponseModel(BaseModel):
    """
    Response model for the `refresh-token` endpoint.

    Args:
        BaseModel (_type_): _description_
    """

    expires_in: str = Field(alias="expiresIn")
    token_type: str
    refresh_token: str = Field(alias="refreshToken")
    id_token: str = Field(alias="idToken")
    user_id: str
    project_id: str
