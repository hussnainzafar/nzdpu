"""
Module for firebase actions oobCode validating functions.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from firebase_admin import auth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.firebase_rest_api_client.models import (
    VerifyPasswordResetResponseModel,
)

from ..utils import (
    check_password_history,
    is_valid_password,
    update_password_history,
)
from ... import settings
from ...db.models import AuthRole, User
from ...dependencies import (
    DbManager,
    FirebaseRESTAPIClient,
    RoleAuthorization,
    initialize_firebase_auth_client,
    initialize_firebase_rest_api_client,
)
from ...schemas.firebase_actions import (
    ConfirmEmailVerificationPayload,
    ConfirmEmailVerificationResponse,
    ConfirmPasswordResetPayload,
    ConfirmPasswordResetResponse,
    VerifyPasswordResetCodePayload,
)

router = APIRouter(
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found."}}
)


@router.post(
    "/verify-password-reset-code",
    response_model=VerifyPasswordResetResponseModel,
)
async def verify_password_reset_code(
    payload: VerifyPasswordResetCodePayload,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    x_qa_key: str = Header(None, alias="x-qa-key"),
) -> VerifyPasswordResetResponseModel:
    """
    Verifies a firebase oobCode sent for a password reset request. Does not change password.

    Parameters
    ----------
        oobCode (str) - The firebase oobCode to verify.
        invalidate (bool) - An optional boolean flag indicating whether to invalidate the link.
    """
    if x_qa_key is not None:
        handle_qa_key_and_invalidate_link(x_qa_key, payload.invalidate)

    verify_response = pb.verify_password_reset_code(oob_code=payload.oobCode)

    return verify_response


@router.post(
    "/confirm-password-reset", response_model=ConfirmPasswordResetResponse
)
async def confirm_password_reset(
    db_manager: DbManager,
    payload: ConfirmPasswordResetPayload,
    firebase_auth_client=Depends(initialize_firebase_auth_client),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    _=Depends(
        RoleAuthorization(
            visible_roles=[
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ],
        )
    ),
) -> ConfirmPasswordResetResponse:
    """
    Verifies a firebase oobCode sent for a password reset request, then
    changes the user's password in firebase.

    Parameters
    ----------
        oobCode (str) - The firebase oobCode to verify.
        password (str) - The new password.
    """

    # Verify oobCode.
    verify_response = pb.verify_password_reset_code(oob_code=payload.oobCode)
    user_email = verify_response.email

    # Fetch Firebase user to be able to fetch user info from our database.
    _fb: auth.Client
    with firebase_auth_client as _fb:  # type: ignore
        fb_user = _fb.get_user_by_email(user_email)

    # Fetch user from our database to check for password history and validity.
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        user = await _session.scalar(
            select(User).where(User.external_user_id == fb_user.uid)
        )

        # Raise error if no user is found.
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "external_user_id": (
                        "No user in the database is found with corresponding"
                        " UID."
                    )
                },
            )

        # Validate password complexity and history.
        password_validation_error = is_valid_password(
            payload.password.get_secret_value(),
            user.name,
            False,
            user_email,
        )

        if password_validation_error is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"password": password_validation_error},
            )

        await check_password_history(
            user.id, payload.password.get_secret_value(), _session
        )

        # Re-initialize firebase auth client to change password in Firebase.
        firebase_auth_client = initialize_firebase_auth_client()
        with firebase_auth_client as _fb:  # type: ignore
            _fb.update_user(
                uid=fb_user.uid, password=payload.password.get_secret_value()
            )

        # Enable user in local database and update password history.
        user.enabled = True
        user.failed_login_attempts = 0

        _session.add(user)

        await update_password_history(
            user.id, payload.password.get_secret_value(), _session
        )

        await _session.commit()

    return ConfirmPasswordResetResponse(**verify_response.model_dump())


@router.post(
    "/confirm-email-verification",
    response_model=ConfirmEmailVerificationResponse,
)
async def confirm_email_verification(
    db_manager: DbManager,
    payload: ConfirmEmailVerificationPayload,
    firebase_auth_client=Depends(initialize_firebase_auth_client),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    _=Depends(
        RoleAuthorization(
            visible_roles=[
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ],
        ),
    ),
    x_qa_key: str = Header(None, alias="x-qa-key"),
) -> ConfirmEmailVerificationResponse:
    """
    Verifies a firebase oobCode for email verification.

    Parameters
    ----------
        oobCode (str) - The firebase oobCode to verify
        invalidate (bool) - An optional boolean flag indicating whether to invalidate the link.
    """

    if x_qa_key:
        handle_qa_key_and_invalidate_link(x_qa_key, payload.invalidate)
    # verify oobCode
    verify_response = pb.update(oob_code=payload.oobCode)
    # get firebase user (get UID)
    _fb: auth.Client
    with firebase_auth_client as _fb:
        fb_user: auth.UserInfo = _fb.get_user_by_email(
            email=verify_response.email
        )
    # user update in DB
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # retrieve user by firebase UID because no other information
        # is provided
        user = await _session.scalar(
            select(User).where(User.external_user_id == fb_user.uid)
        )
        # raise if no user is found
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "external_user_id": (
                        "Received oobCode for email verification/reset,"
                        " but no user in the database is found with"
                        " corresponding UID."
                    )
                },
            )
        # update user email
        user.email = verify_response.email
        user.email_verified = verify_response.email_verified
        _session.add(user)
        await _session.commit()

    return ConfirmEmailVerificationResponse(
        email=verify_response.email,
        emailVerified=verify_response.email_verified,
    )


def handle_qa_key_and_invalidate_link(x_qa_key: str, invalidate: bool):
    """
    Handles the QA key and invalidation link logic.

    Parameters
    ----------
        x_qa_key (str) - The x-qa-key header value.
        invalidate (bool) - Flag to indicate whether to invalidate the link.
    """
    if x_qa_key == settings.application.x_qa_key:
        if invalidate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"oobCode": "The action code has expired."},
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "global": "You are not authorized to perform this action."
            },
        )
