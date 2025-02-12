"""
Schemas for firebase action oobCode validation endpoints.
"""

from pydantic import BaseModel, EmailStr, SecretStr


class ConfirmEmailVerificationPayload(BaseModel):
    """
    Schema for confirm-email-verification endpoint request body.
    """

    oobCode: str
    invalidate: bool = False


class ConfirmPasswordResetPayload(ConfirmEmailVerificationPayload):
    """
    Schema for confirm-password-reset endpoint request body.
    """

    password: SecretStr


class ConfirmEmailVerificationResponse(BaseModel):
    """
    Schema for confirm-email-verification endpoint response.
    """

    email: EmailStr
    emailVerified: bool


class ConfirmPasswordResetResponse(BaseModel):
    """
    Schema for confirm-password-reset endpoint response.
    """

    email: EmailStr


class VerifyPasswordResetCodePayload(BaseModel):
    """
    Schema for verify-password-reset-code endpoint request body.
    """

    oobCode: str
    invalidate: bool = False
