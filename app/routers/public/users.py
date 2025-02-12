"""
Module for user public APIs which do not require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin._auth_client import Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthMode, AuthRole, Group, PasswordHistory, User
from app.dependencies import (
    DbManager,
    FirebaseRESTAPIClient,
    RoleAuthorization,
    get_email_verification_link,
    get_password_verification_link,
    get_system_qa_key_from_header,
    initialize_firebase_auth_client,
    initialize_firebase_rest_api_client,
)
from app.schemas.user import (
    UserCreate,
    UserIdOnly,
    UserLoginDataModel,
)
from app.utils import encrypt_password

from ..utils import (
    get_updated_user_name_if_same_with_mail,
    is_string_ascii_only,
    is_valid_password,
)

router = APIRouter(
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found."}}
)


@router.post("/register", response_model=UserIdOnly)
async def register_user(
    db_manager: DbManager,
    user: UserCreate,
    firebase_auth_client=Depends(initialize_firebase_auth_client),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    _=Depends(RoleAuthorization(visible_roles=["__NOT_A_USER__"])),
    x_qa_key=Depends(get_system_qa_key_from_header),
) -> UserIdOnly:
    """
    Register a new user.

    Parameters
    ----------
        user - User input data.
    Returns
    -------
        The user's details.
    """
    user.name = await get_updated_user_name_if_same_with_mail(
        user.name, user.email
    )
    if not is_string_ascii_only(user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"email": "Email can only contain English letters."},
        )

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        db_user_by_email = await _session.scalar(
            select(User).where(User.email == user.email)
        )

        if db_user_by_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "email": "Email already in use. Try logging in instead."
                },
            )

        db_user_by_name = await _session.scalar(
            select(User).where(User.name == user.name)
        )

        if db_user_by_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "global": "User already exists. Try logging in instead."
                },
            )

        password_validation = is_valid_password(
            user.password, user.name, False, user.email
        )
        if password_validation is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"password": password_validation},
            )
        # add user to firebase store
        _fb: Client
        with firebase_auth_client as _fb:
            firebase_user = _fb.create_user(
                email=user.email,
                password=user.password,
            )

        # create new user
        new_user: User = User(**user.model_dump(exclude={"hashed_password"}))
        new_user.auth_mode = AuthMode.FIREBASE
        new_user.external_user_id = str(firebase_user.uid)
        new_user.password = None
        new_user.organization_type = user.organization_type
        _session.add(new_user)

        if not new_user.groups:
            role = AuthRole.DATA_EXPLORER
            group = await _session.scalar(select(Group).filter_by(name=role))
            if group:
                # assign role to user
                new_user.groups.append(group)

        # Commit user to retrieve its id.
        await _session.commit()

        history_pass = encrypt_password(user.password)
        new_history_entry = PasswordHistory(
            user_id=new_user.id, encrypted_password=history_pass
        )
        _session.add(new_history_entry)

        await _session.commit()

    # get token
    fb_user = pb.sign_in_with_email_and_password(
        email=user.email, password=user.password
    )
    token = fb_user.id_token

    if x_qa_key and settings.application.x_qa_key == x_qa_key:
        link = get_email_verification_link(user.email)
        return UserIdOnly(id=new_user.id, verification_link=link)

    # send verification email
    pb.send_email_verification(token)

    return new_user


@router.post("/reset-password", response_model=UserIdOnly)
async def reset_password(
    email: str,
    db_manager: DbManager,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    _=Depends(RoleAuthorization(visible_roles=["__NOT_A_USER__"])),
    x_qa_key=Depends(get_system_qa_key_from_header),
):
    """
    Triggers firebase's send_password_reset_email function, which sends
    a password reset link to the provided email address.

    Parameters
    ----------
        email - The users' email.
    Returns
    -------
        The user ID of the user associated with the provided email.
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        user: User = await _session.scalar(
            select(User).where(User.email == email)
        )

    if not user:
        # user not found
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "email": (
                    "If a matching account was found, an email was sent to"
                    f" {email} to allow you to reset your password. If you do"
                    " not receive the email, please check your Spam folder,"
                    " click below to resend the link, or consider "
                    "{{REGISTER_LINK}}"
                )
            },
        )

    if user.auth_mode == AuthMode.FIREBASE:
        # Send verification email
        pb.send_password_reset_email(str(user.email))
        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            link = get_password_verification_link(user.email)
            return UserIdOnly(id=user.id, verification_link=link)

        return user


@router.post("/send-email-verification", response_model=UserIdOnly)
async def send_email_verification(
    user_data: UserLoginDataModel,
    db_manager: DbManager,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    _=Depends(
        RoleAuthorization(
            [
                "__NOT_A_USER__",
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
            ]
        )
    ),
    x_qa_key=Depends(get_system_qa_key_from_header),
):
    """
    Sends an email verification link to the provided email address.

    Parameters
    ----------
        user_data - The users' email and password.
    Returns
    -------
        The user ID of the user associated with the provided email.
    """

    async with db_manager.get_session() as _session:
        user: User = await _session.scalar(
            select(User).where(User.email == user_data.email)
        )

    if user and user.auth_mode == AuthMode.FIREBASE:
        # get token
        fb_user = pb.sign_in_with_email_and_password(
            email=user_data.email, password=user_data.password
        )
        token = fb_user.id_token

        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            link = get_email_verification_link(user.email)
            return UserIdOnly(id=user.id, verification_link=link)

        # Send verification email
        pb.send_email_verification(token)

        return user

    raise HTTPException(
        detail={
            "email": (
                "Incorrect email or password. Please try again or reset your"
                " password."
            )
        },
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
