"""Token schemas"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from .user import AuthMode

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class Token(BaseModel):
    """
    Schema for token based authentication
    """

    access_token: str
    refresh_token: str
    token_type: str
    email_verified: bool


class BaseTokenData(BaseModel):
    """
    Common schema for token data.
    """

    sub: str
    iat: datetime
    auth_mode: AuthMode = AuthMode.LOCAL


class AccessTokenData(BaseTokenData):
    """
    Schema for token data
    """

    exp: datetime


class RefreshTokenData(BaseTokenData):
    """
    Schema for token data
    """

    exp: datetime
    uid: str


class RefreshTokenRequest(BaseModel):
    """
    Schema for refresh token request.
    """

    refresh_token: str


class TokenValidationErrorEnum(str, Enum):
    """
    Enumerators for token validation error codes.
    """

    INVALID = "INVALID"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED = "EXPIRED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
