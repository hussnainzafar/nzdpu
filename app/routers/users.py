"""Users router."""

from __future__ import annotations

import csv
import json
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app import settings
from app.db.models import (
    AuthMode,
    AuthRole,
    Group,
    Organization,
    PasswordHistory,
    Permission,
    User,
    UserPublisherRequest,
    user_group,
)
from app.dependencies import (
    DbManager,
    FirebaseRESTAPIClient,
    RoleAuthorization,
    RoleAuthorizationForMultipleAuth,
    get_current_user_from_multiple_auth,
    get_email_verification_link,
    get_system_qa_key_from_header,
    initialize_firebase_auth_client,
    initialize_firebase_rest_api_client,
    verify_token,
)
from app.routers.utils import is_valid_password, update_user_data_last_accessed
from app.schemas import user as user_schema
from app.service.user_service import UserService

from ..loggers import get_nzdpu_logger
from ..schemas.user import (
    NotificationSignupResponse,
    UserDeleteResponse,
    UserListResponse,
)
from ..utils import check_password, encrypt_password
from .utils import (
    ErrorMessage,
    check_admin_access_rights,
    check_password_history,
    load_user,
    update_password_history,
)

# creates the router
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(verify_token)],
    responses={404: {"description": "Not found"}},
)
logger = get_nzdpu_logger()


async def update_groups_association(
    groups: list, user: User, session: AsyncSession
):
    """
    If groups is not an empty list, iterate over it and for each group:
     - if the group does not exist, create it in the DB first
     - update the association with the new user and groups

    Parameters
    ----------
        groups - the list of groups
        user - the new user

    Returns
    -------
        The updated user
    """
    # check if groups are specified in the request body
    if groups:
        for group in groups:
            stmt = select(Group).where(Group.name == group.name)
            result = await session.execute(stmt)
            db_group = result.scalars().first()
            # create new group if group doesn't exist
            if db_group is None:
                # create new group
                db_group = Group(**group.dict())
                session.add(db_group)

            user.groups.append(db_group)
    return user


async def update_user_email(
    token: str,
    pb: FirebaseRESTAPIClient,
    db_user: User,
    user_data: user_schema.UserUpdate,
    x_qa_key: str | None = None,
) -> tuple[str, str | None]:
    """
    Updates the user email in the database and in Firebase (if the user
    is also a Firebase user).

    Args:
        token (str): The user's token from the request.
        pb (FirebaseRESTAPIClient): Firebase REST API client.
        db_user (User): The user record from the database.
        user_data (user_schema.UserUpdate): the new user's data from the
            request payload.

    Returns:
        tuple[str, str | None]: The new Firebase tokens if the
            user is a Firebase user, `token, None,` otherwise.
    """
    # update the user's email in the DB
    db_user.email = user_data.email
    if db_user.auth_mode == AuthMode.FIREBASE:
        # update user email in firebase
        user_info = pb.update(
            id_token=token, email=user_data.email, return_secure_token=True
        )
        db_user.email_verified = user_info.email_verified

        if x_qa_key is None:
            pb.send_email_verification(user_info.id_token)
        return user_info.id_token, user_info.refresh_token

    return (
        token,
        None,
    )


async def update_user_password(
    token: str,
    pb: FirebaseRESTAPIClient,
    db_user: User,
    new_password: SecretStr,
    current_password: str,
    email: str | None = None,
) -> tuple[str, str | None]:
    """
    Updates the user password in the database and in Firebase (if the
    user is also a Firebase user).

    Args:
        token (str): The user's token from the request.
        pb (FirebaseRESTAPIClient): Firebase REST API Client.
        db_user (User): The user record from the database.
        new_password (SecretStr): The user's new password.
        current_password (str): The user's current password.
        email (str | None, optional): The user's email address, used
            for Firebase users to authenticate and check the provided
            current password matches the one stored in FIrebase.
            Defaults to None if the user is not a Firebase user.

    Raises:
        HTTPException: 400 BAD REQUEST if passwords don't match.

    Returns:
        tuple[str, str | None]: The new Firebase tokens if the
            user is a Firebase user, `token, None,` otherwise.
    """
    if db_user.auth_mode == AuthMode.LOCAL:
        # check current password matches with stored hash
        if not check_password(
            pwd=current_password, hashed_pwd=db_user.password
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "current_password": ErrorMessage.PASSWORD_DOES_NOT_MATCH
                },
            )
        # hash new password
        new_hashed_pass = encrypt_password(new_password.get_secret_value())
        # save new hashed password to user db
        db_user.password = new_hashed_pass
    elif db_user.auth_mode == AuthMode.FIREBASE:
        # attempt login to check current password is good
        pb.sign_in_with_email_and_password(
            email=str(email), password=current_password
        )
        # update firebase password
        user_info = pb.update(
            id_token=token,
            password=new_password.get_secret_value(),
            return_secure_token=True,
        )
        db_user.password = None

        return user_info.id_token, user_info.refresh_token

    return token, None


@router.get("", response_model=user_schema.PaginatedUserGet)
async def list_users(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    group: user_schema.GroupFilter | None = None,
    order: str = "asc",
    start: int = 0,
    limit: int = 1000,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Return the list of all users.

    Parameters
    ----------
    filter_by - filter as dict e.g. {"name":"sample"}
    order_by - list of ordering fields e.g. ["name","id"]
    group - filter by group name
    order - default "asc", can apply "asc" and "desc"
    start - starting index for the users list
    limit - maximum number of users to return

    Returns
    -------
        a dictionary containing the list of users and pagination information
    """

    # load users
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # parse the filter_by and order_by parameters
        filter_dict = {}
        order_by_list = []
        if filter_by:
            try:
                filter_dict = json.loads(filter_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid filter_by format. Must be a valid JSON"
                        " string."
                    ),
                ) from exc
        if order_by:
            try:
                order_by_list = json.loads(order_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid order_by format. Must be a valid JSON list of"
                        " strings."
                    ),
                ) from exc
        # load users

        query = select(User).options(joinedload(User.groups))
        # Filter by group if specified
        if group:
            query = query.join(User.groups).filter(Group.name == group)

        # apply filtering from filter_by query params
        if "name" in filter_dict:
            query = query.where(User.name.ilike(f"%{filter_dict['name']}%"))
        if "first_name" in filter_dict:
            query = query.where(
                User.first_name.ilike(f"%{filter_dict['first_name']}%")
            )
        if "last_name" in filter_dict:
            query = query.where(
                User.last_name.ilike(f"%{filter_dict['last_name']}%")
            )
        if "enabled" in filter_dict:
            try:
                enabled = filter_dict["enabled"].lower() == "true"
                query = query.where(User.enabled == enabled)
            except UnboundLocalError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid value for 'enabled'. Must be either 'true' or"
                        " 'false'."
                    ),
                ) from exc

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    User.id.asc() if order == "asc" else User.id.desc()
                )
            elif field == "name":
                query = query.order_by(
                    User.name.asc() if order == "asc" else User.name.desc()
                )
            elif field == "first_name":
                query = query.order_by(
                    User.first_name.asc()
                    if order == "asc"
                    else User.first_name.desc()
                )
            elif field == "last_name":
                query = query.order_by(
                    User.last_name.asc()
                    if order == "asc"
                    else User.last_name.desc()
                )
            elif field == "enabled":
                query = query.order_by(
                    User.enabled.asc()
                    if order == "asc"
                    else User.enabled.desc()
                )
            elif field == "created_on":
                query = query.order_by(
                    User.created_on.asc()
                    if order == "asc"
                    else User.created_on.desc()
                )
            elif field == "last_access":
                query = query.order_by(
                    User.last_access.asc()
                    if order == "asc"
                    else User.last_access.desc()
                )
            elif field == "email":
                query = query.order_by(
                    User.email.asc() if order == "asc" else User.email.desc()
                )

            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}. Must be id, name,"
                        " first_name, last_name, enabled, created_on, or"
                        " last_access"
                    ),
                )

        query = query.where(User.deleted == False)

        total_stmt = query.with_only_columns(
            func.count(), maintain_column_froms=True
        ).order_by(None)

        query = query.offset(start).limit(limit)

        result = await _session.execute(query)
        records = result.unique().scalars().all()

        total_result = await _session.execute(total_stmt)
        total = total_result.scalar_one()

    # Prepare response
    response = {
        "start": start,
        "end": start + len(records),
        "total": total,
        "items": records,
    }

    return response


@router.get("/standalone", response_model=list[user_schema.UserStandalone])
async def list_standalone_users(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
) -> list[user_schema.UserStandalone]:
    """
    Get the list of users who don't belong to any group, and with no
    associated permissions.

    Returns
    -------
        The list of standalone users.
    """

    _session: AsyncSession
    standalone_users: list[user_schema.UserStandalone] = []
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        users = await _session.stream_scalars(
            select(User)
            .options(selectinload(User.groups))
            .filter(~User.groups.any())
        )
        async for user in users:
            # check not directly bound to a permission
            result = await _session.scalars(
                select(Permission).where(Permission.user_id == user.id)
            )
            permissions = result.unique().all()
            if not permissions:
                standalone_users.append(user)

    return standalone_users


@router.get("/current_user", response_model=user_schema.UserGet)
async def get_current(
    db_manager: DbManager,
    current_user: User = Depends(get_current_user_from_multiple_auth),
):
    """
    Returns details of the current user.

    Returns
    -------
        current user data
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        # load current user
        user = await load_user(current_user.id, _session)

        if user.organization_id:
            # load linked company
            organization = await _session.scalar(
                select(Organization).where(
                    Organization.id == user.organization_id
                )
            )
            if organization:
                # add company data to the result
                user.lei = organization.lei

        return user


@router.get("/get-access-key", response_model=user_schema.UserApiKeyUpdate)
async def get_access_key(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                AuthRole.ADMIN,
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
            ],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Return the api_key from current user.

    Returns
    -------
        api_key from current user
    """
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # load the existing user from the DB
        db_user = await load_user(current_user.id, _session)
        if not db_user.api_key:
            # Generate a new API key
            api_key = secrets.token_hex(16)
            db_user.api_key = api_key

            _session.add(db_user)
            await _session.commit()
    return user_schema.UserApiKeyUpdate(access_key=db_user.api_key)


@router.get("/revoke-access-key", response_model=user_schema.UserApiKeyUpdate)
async def revoke_access_key(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                AuthRole.ADMIN,
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
            ],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
     Revoke the api_key from current user.

    Returns
    -------
        the revoked api_key from current user
    """
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # load the existing user from the DB
        db_user = await load_user(current_user.id, _session)
        if db_user.api_key:
            # Revoke the user's API key by setting it to None
            db_user.api_key = None

            _session.add(db_user)
            await _session.commit()
        api_key_str = "" if db_user.api_key is None else db_user.api_key
    return user_schema.UserApiKeyUpdate(access_key=api_key_str)


@router.post(
    "/notifications-signup", response_model=NotificationSignupResponse
)
async def notifications_signup(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                AuthRole.ADMIN,
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
            ],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Signs a User up for notifications

    Returns
    -------
    The ID of the user
    Notification bool
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_user = await load_user(current_user.id, _session)
        db_user.notifications = True
        _session.add(db_user)
        await _session.commit()
        return NotificationSignupResponse(
            user_id=db_user.id, notifications=db_user.notifications
        )


@router.get("/notifications-signup", response_model=NotificationSignupResponse)
async def get_notifications_signup(
    db_manager: DbManager,
    current_user: User = Depends(get_current_user_from_multiple_auth),
):
    """
    Get the status of the user's notification signup

    Returns
    -------
    The ID of the user
    Notification bool
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # Return the current user ID and notifications sign-up status
        return NotificationSignupResponse(
            user_id=current_user.id, notifications=current_user.notifications
        )


@router.post(
    "/notifications-signup/revoke", response_model=NotificationSignupResponse
)
async def revoke_notifications_signup(
    db_manager: DbManager,
    current_user: User = Depends(get_current_user_from_multiple_auth),
):
    """
    Revokes a user's sign up for notifications

    Returns
    -------
    The ID of the user
    Notification bool
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        # load user
        db_user = await load_user(current_user.id, _session)
        # revoke notifications by setting it to false
        db_user.notifications = False
        # update the user in the database
        _session.add(db_user)
        # commit changes
        await _session.commit()
        return NotificationSignupResponse(
            user_id=db_user.id, notifications=db_user.notifications
        )


@router.get("/tracking/download", response_class=FileResponse)
async def download_tracking_data_csv(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorizationForMultipleAuth(
            [
                AuthRole.ADMIN,
            ],
        )
    ),
):
    user_service = UserService(db_manager)
    temp_file = await user_service.download_tracking_data_csv()
    now = datetime.now()
    return FileResponse(
        path=temp_file.name,
        media_type="text/csv",
        filename=f"nzdpu_users_api_tracking_{now.strftime('%Y-%m-%d_%H:%M:%S')}.csv",
    )


@router.get("/notifications-signup/download", response_class=FileResponse)
async def download_notification_users_csv(
    db_manager: DbManager,
    _=Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    async with db_manager.get_session() as _session:
        stmt = select(User).where(User.notifications)
        users = await _session.execute(stmt)
        user_data = [(user.id, user.email) for user in users.scalars()]
        temp_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        with open(temp_file.name, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "user_id",
                    "email",
                ]
            )
            for item in user_data:
                writer.writerow(item)

            return FileResponse(
                path=temp_file.name,
                media_type="application/octet-stream",
                filename="nzdpu_users_with_notification.csv",
            )


@router.get("/{user_id}", response_model=user_schema.UserGet)
async def get_user(
    user_id: int,
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Return the details of a user

    Parameters
    ----------
        user_id - user identifier
    Returns
    -------
        user data
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        user_data = await load_user(user_id, _session)

        if user_data.organization_id:
            # load linked company
            organization = await _session.scalar(
                select(Organization).where(
                    Organization.id == user_data.organization_id
                )
            )
            if organization:
                # add company data to the result
                user_data.lei = organization.lei

        return user_data


@router.post(
    "/request-publisher-access",
    response_model=user_schema.UserPublisherResponse,
)
async def request_publisher_access(
    db_manager: DbManager,
    payload: user_schema.UserPublisherRequest,
    current_user: User = Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
) -> user_schema.UserPublisherResponse:
    """
    Requests grants for a user for publishing on behalf of a company.
    The user requesting access is assumed to be the currently logged-in
    one.

    Parameters
    ----------
        company_lei (string, required): LEI of the company we are
            requesting publisher access for.
        company_type (string, optional): Type of the company.
        company_website (string, optional): Link to company web site.
        role (string, optional): User role.
        linkedin_link (string, optional): Link to user's LinkedIn
            profile.

    Returns
    -------
        UserPublisherResponse - The request status.
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check if requests already present
        request = await _session.scalar(
            select(UserPublisherRequest).where(
                UserPublisherRequest.user_id == current_user.id
            )
        )
        if not request:
            # create request
            request = UserPublisherRequest(
                user_id=current_user.id,
                role=payload.role,
                linkedin_link=payload.linkedin_link,
                company_lei=payload.company_lei,
                company_type=payload.company_type,
                company_website=payload.company_website,
            )

            _session.add(request)
            await _session.commit()

    return user_schema.UserPublisherResponse(status=request.status)


@router.post("", response_model=user_schema.UserApiCreateResponse)
async def create_user(
    user: user_schema.UserCreate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
    firebase_auth_client=Depends(initialize_firebase_auth_client),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
):
    """
    Creates a new user

    Parameters
    ----------
        user - user input data
    Returns
    -------
        the user's id, auth_mode and firebase user ID (external_user_id)
    """

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

    _session: AsyncSession
    # empty incoming groups list so to not upset SQLAlchemy
    groups = list(user.groups)
    user.groups = []

    # create new user, with optional groups
    async with db_manager.get_session() as _session:
        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        new_user = await update_groups_association(
            groups,
            User(**user.model_dump(exclude={"hashed_password"})),
            _session,
        )
        if not new_user.groups:
            group: Group | None = None
            role = AuthRole.DATA_EXPLORER
            group = await _session.scalar(select(Group).filter_by(name=role))
            if group:
                # assign role to user
                new_user.groups.append(group)
        new_user.auth_mode = AuthMode.FIREBASE
        history_pass = encrypt_password(str(new_user.password))
        # we don't need storing password for Firebase users
        new_user.password = None
        _session.add(new_user)
        await _session.commit()

        # add password to user password history
        new_history_entry = PasswordHistory(
            user_id=new_user.id, encrypted_password=history_pass
        )
        _session.add(new_history_entry)
        await _session.commit()

        # add user to firebase store
        _fb: auth.Client
        with firebase_auth_client as _fb:
            firebase_user: auth.UserRecord = _fb.create_user(
                email=user.email,
                password=user.password,
            )
        # set external_user_id after creation of the user in Firebase.
        # this kind of immediate update of the user is necessary, since
        # the creation of the user in firebase should be made after
        # successful storing of the new user in the WIS DB, to avoid
        # databases to lose alignment, and the firebase user UID won't
        # be available until the user is created
        new_user.external_user_id = str(firebase_user.uid)
        _session.add(new_user)
        await _session.commit()

    # get token
    firebase_user_info = pb.sign_in_with_email_and_password(
        email=user.email, password=user.password
    )
    token = firebase_user_info.id_token

    # send verification email
    pb.send_email_verification(token)
    return user_schema.UserApiCreateResponse(
        id=new_user.id,
        auth_mode=new_user.auth_mode,
        external_user_id=new_user.external_user_id,
    )


@router.patch("/current", response_model=user_schema.UserUpdateResponse)
async def update_current_user(
    request: Request,
    user_data: user_schema.UserUpdate,
    db_manager: DbManager,
    current_user: User = Depends(get_current_user_from_multiple_auth),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    x_qa_key=Depends(get_system_qa_key_from_header),
):
    """
    Update an existing user

    Parameters
    ----------
        user_data - user input data
    Returns
    -------
        the updated user
    """
    _session: AsyncSession
    if user_data.email is not None and current_user.groups:
        if current_user.groups[0].name == AuthRole.SCHEMA_EDITOR:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "user": (
                        f"User {current_user.name} is not allowed to update"
                        " user email"
                    )
                },
            )

    # get token for email and password change
    _, token = request.headers["authorization"].split()
    refresh_token = None

    # load the existing user from the DB
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        db_user = await load_user(current_user.id, _session)

    # update user, groups and associations
    groups = []
    if db_user.auth_mode == AuthMode.LOCAL:
        # check current password matches with stored hash

        if user_data.current_password is not None:
            if not check_password(
                pwd=user_data.current_password, hashed_pwd=db_user.password
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "password": "Incorrect password. Please try again or reset your password."
                    },
                )
    if user_data.groups:
        if AuthRole.ADMIN not in [g.name for g in current_user.groups]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "user": "Only admin users are allowed to edit user groups."
                },
            )
        groups = list(user_data.groups)
        user_data.groups = []
        if groups:
            async with db_manager.get_session() as _session:
                db_user = await update_groups_association(
                    groups, db_user, _session
                )
    # update organization type
    if user_data.organization_type is not None:
        db_user.organization_type = user_data.organization_type
    # update email
    recovery_link = None
    verification_link = None
    if user_data.email is not None and user_data.email != db_user.email:
        # retrieve updated tokens from Firebase API if Firebase user
        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            recovery_link = get_email_verification_link(db_user.email)
        token, refresh_token = await update_user_email(
            token=token,
            pb=pb,
            db_user=db_user,
            user_data=user_data,
            x_qa_key=x_qa_key,
        )
        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            verification_link = get_email_verification_link(user_data.email)
    # update password
    if user_data.current_password and user_data.new_password:
        # validate password complexity
        password_validation_error = is_valid_password(
            user_data.new_password.get_secret_value(),
            db_user.name,
            False,
            db_user.email,
        )

        if password_validation_error is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"new_password": password_validation_error},
            )

        # check that the new password doesn't match any of the previous ones
        async with db_manager.get_session() as _session:
            await check_password_history(
                user_id=current_user.id,
                new_password=user_data.new_password.get_secret_value(),
                session=_session,
            )

        # retrieve updated tokens from Firebase API if Firebase user
        token, refresh_token = await update_user_password(
            token=token,
            pb=pb,
            db_user=db_user,
            new_password=user_data.new_password,
            current_password=user_data.current_password,
            email=db_user.email,
        )
        # update user password history with hashed new password
        async with db_manager.get_session() as _session:
            await update_password_history(
                user_id=current_user.id,
                new_password=user_data.new_password.get_secret_value(),
                session=_session,
            )
    # init organization LEI for return of LEI in user response
    organization_lei = None
    # set new values for user from update data
    user_update = user_data.model_dump(exclude_unset=True, exclude={"groups"})

    for key, value in user_update.items():
        setattr(db_user, key, value)
    # update user in DB
    async with db_manager.get_session() as _session:
        _session.add(db_user)
        await _session.commit()
        if db_user.organization_id:
            # load linked company to set lei in response
            organization = await _session.scalar(
                select(Organization).where(
                    Organization.id == db_user.organization_id
                )
            )
            if organization:
                organization_lei = organization.lei

    # set user response + tokens and lei
    user_update_response = user_schema.UserGet.model_validate(
        db_user
    ).model_dump() | {
        "token": token,
        "refresh_token": refresh_token,
        "lei": organization_lei,
        "recovery_link": recovery_link,
        "verification_link": verification_link,
    }

    return user_schema.UserUpdateResponse(**user_update_response)


@router.patch("/{user_id}", response_model=user_schema.UserUpdateResponse)
async def update_user(
    request: Request,
    user_id: int,
    user_data: user_schema.UserUpdate,
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
            show_for_firebase=True,
        )
    ),
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    x_qa_key=Depends(get_system_qa_key_from_header),
):
    """
    Update an existing user

    Parameters
    ----------
        user_id - identifier of the user we want to update
        user_data - user input data
    Returns
    -------
        the updated user
    """
    _session: AsyncSession
    if user_data.email is not None and current_user.groups:
        if current_user.groups[0].name == AuthRole.SCHEMA_EDITOR:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "user": (
                        f"User {current_user.name} is not allowed to update"
                        " user email"
                    )
                },
            )
    # If user is not requesting itself it needs to be an ADMIN.
    if current_user and current_user.id != user_id:
        await RoleAuthorization([AuthRole.ADMIN]).check_user_roles(
            db_manager=db_manager, request=request, pb=pb
        )

    # get token for email and password change
    _, token = request.headers["authorization"].split()
    refresh_token = None

    # load the existing user from the DB
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        db_user = await load_user(user_id, _session)

    # update user, groups and associations
    groups = []
    if db_user.auth_mode == AuthMode.LOCAL:
        # check current password matches with stored hash

        if user_data.current_password is not None:
            if not check_password(
                pwd=user_data.current_password, hashed_pwd=db_user.password
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "password": "Incorrect password. Please try again or reset your password."
                    },
                )
    if user_data.groups:
        if AuthRole.ADMIN not in [g.name for g in current_user.groups]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "user": "Only admin users are allowed to edit user groups."
                },
            )
        groups = list(user_data.groups)
        user_data.groups = []
        if groups:
            async with db_manager.get_session() as _session:
                db_user = await update_groups_association(
                    groups, db_user, _session
                )
    # update organization type
    if user_data.organization_type is not None:
        db_user.organization_type = user_data.organization_type
    # update email
    recovery_link = None
    verification_link = None
    if user_data.email is not None and user_data.email != db_user.email:
        # retrieve updated tokens from Firebase API if Firebase user
        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            recovery_link = get_email_verification_link(db_user.email)
        token, refresh_token = await update_user_email(
            token=token,
            pb=pb,
            db_user=db_user,
            user_data=user_data,
            x_qa_key=x_qa_key,
        )
        if x_qa_key and settings.application.x_qa_key == x_qa_key:
            verification_link = get_email_verification_link(user_data.email)
    # update password
    if user_data.current_password and user_data.new_password:
        # validate password complexity
        password_validation_error = is_valid_password(
            user_data.new_password.get_secret_value(),
            db_user.name,
            False,
            db_user.email,
        )

        if password_validation_error is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"new_password": password_validation_error},
            )

        # check that the new password doesn't match any of the previous ones
        async with db_manager.get_session() as _session:
            await check_password_history(
                user_id=user_id,
                new_password=user_data.new_password.get_secret_value(),
                session=_session,
            )

        # retrieve updated tokens from Firebase API if Firebase user
        token, refresh_token = await update_user_password(
            token=token,
            pb=pb,
            db_user=db_user,
            new_password=user_data.new_password,
            current_password=user_data.current_password,
            email=db_user.email,
        )
        # update user password history with hashed new password
        async with db_manager.get_session() as _session:
            await update_password_history(
                user_id=user_id,
                new_password=user_data.new_password.get_secret_value(),
                session=_session,
            )
    # init organization LEI for return of LEI in user response
    organization_lei = None
    # set new values for user from update data
    user_update = user_data.model_dump(exclude_unset=True, exclude={"groups"})

    for key, value in user_update.items():
        setattr(db_user, key, value)
    # update user in DB
    async with db_manager.get_session() as _session:
        _session.add(db_user)
        await _session.commit()
        if db_user.organization_id:
            # load linked company to set lei in response
            organization = await _session.scalar(
                select(Organization).where(
                    Organization.id == db_user.organization_id
                )
            )
            if organization:
                organization_lei = organization.lei

    # set user response + tokens and lei
    user_update_response = user_schema.UserGet.model_validate(
        db_user
    ).model_dump() | {
        "token": token,
        "refresh_token": refresh_token,
        "lei": organization_lei,
        "recovery_link": recovery_link,
        "verification_link": verification_link,
    }

    return user_schema.UserUpdateResponse(**user_update_response)


@router.get("/{user_id}/reset-password", response_model=user_schema.UserGet)
async def reset_password(
    request: Request,
    user_id: int,
    db_manager: DbManager,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Send reset password email to user

    Parameters
    ----------
        user_id - user identifier
    Returns
    -------
        user data
    """
    # If user is not requesting for itself it needs to be an ADMIN.
    if current_user and current_user.id != user_id:
        await RoleAuthorization([AuthRole.ADMIN]).check_user_roles(
            db_manager=db_manager, request=request, pb=pb
        )

    # get user from database
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        user = await load_user(user_id, _session)

    if user.auth_mode == AuthMode.FIREBASE:
        # Send verification email
        pb.send_password_reset_email(str(user.email))

        return user

    raise HTTPException(
        detail=ErrorMessage.ID_DOES_NOT_BELONG_TO_FIREBASE_USER,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@router.get("/{user_id}/inactive", response_model=list[UserListResponse])
async def list_inactive_users(
    db_manager: DbManager,
    inactive_for: int = 365,
    current_user: User = Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Return the list of inactive users (last activity more than a year ago).

    Parameters
    ----------
    inactive_for: amount of days user has been inactive for

    Returns
    -------
    A dictionary containing the list of inactive users and pagination information
    """

    _session: AsyncSession
    result = []
    async with db_manager.get_session() as _session:
        # Calculate the date 2 years ago from the current date
        two_years_ago = datetime.now() - timedelta(days=inactive_for)
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        stmt = (
            select(User)
            .filter(User.data_last_accessed <= two_years_ago)
            .options(selectinload(User.groups))
        )
        # pylint: disable=not-callable
        total_stmt = (
            select(func.count())
            .select_from(User)
            .where(User.data_last_accessed <= two_years_ago)
        )
        total = await _session.execute(total_stmt)
        inactive_users = await _session.stream_scalars(stmt.order_by(User.id))

        async for user in inactive_users:
            result.append(user_schema.UserGet.model_validate(user))
        response_data = [
            UserListResponse(
                items=result,
                total=total.scalar_one(),
            )
        ]
        return response_data


@router.delete("/current", response_model=UserDeleteResponse)
async def vanish_from_existence(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
    firebase_auth_client=Depends(initialize_firebase_auth_client),
):
    """
    Delete you from firebase and delete all personal data from the user in our database

    Returns
    -------
    The ID of the deleted user
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_user = await load_user(current_user.id, _session)
        if db_user.auth_mode == AuthMode.FIREBASE and db_user.external_user_id:
            # Delete the user from Firebase
            _fb: auth.Client
            with firebase_auth_client as _fb:
                try:  # if the user does not exist we receive an exception
                    _fb.get_user(uid=db_user.external_user_id)
                # do not raise and do not delete if user is not found
                except FirebaseError as err:
                    if err.code == "NOT_FOUND":
                        logger.debug(f"No user in firebase {err}")
                else:
                    _fb.delete_user(uid=db_user.external_user_id)

        # Begin replacing sensitive user data with generic data
        def deleted_value():
            return f"deleted_{str(uuid.uuid4())[:24]}"

        db_user.first_name = deleted_value()
        db_user.last_name = deleted_value()
        db_user.email = deleted_value()
        db_user.name = deleted_value()
        db_user.password = deleted_value()
        db_user.api_key = deleted_value()
        # Set the user to disabled
        db_user.enabled = False
        db_user.deleted = True
        # Update the user in the database
        _session.add(db_user)
        await _session.commit()
        # Return the updated deleted user info
        response_data: dict[str, int | bool] = {
            "id": db_user.id,
            "deleted": db_user.deleted,
        }
        return response_data


@router.delete("/{user_id}", response_model=UserDeleteResponse)
async def delete_user(
    db_manager: DbManager,
    user_id: int,
    firebase_auth_client=Depends(initialize_firebase_auth_client),
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR],
            visible_roles=[AuthRole.ADMIN],
        )
    ),
):
    """
    Delete a user from firebase and delete all personal data from the user in our database

    Parameters
    ----------
    user_id: ID of the user to be deleted

    Returns
    -------
    The ID of the deleted user
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_user = await load_user(user_id, _session)
        if db_user.auth_mode == AuthMode.FIREBASE and db_user.external_user_id:
            # Delete the user from Firebase
            _fb: auth.Client
            with firebase_auth_client as _fb:
                try:  # if the user does not exist we receive an exception
                    _fb.get_user(uid=db_user.external_user_id)
                # do not raise and do not delete if user is not found
                except FirebaseError as err:
                    if err.code == "NOT_FOUND":
                        logger.debug(f"No user in firebase {err}")
                else:
                    _fb.delete_user(uid=db_user.external_user_id)

        # Begin replacing sensitive user data with generic data
        def deleted_value():
            return f"deleted_{str(uuid.uuid4())[:24]}"
            db_user.first_name = deleted_value()

        db_user.last_name = deleted_value()
        db_user.email = deleted_value()
        db_user.name = deleted_value()
        db_user.password = deleted_value()
        db_user.api_key = deleted_value()
        # Set the user to disabled
        db_user.enabled = False
        db_user.deleted = True
        # Update the user in the database
        _session.add(db_user)
        await _session.commit()
        # Return the updated deleted user info
        response_data: dict[str, int | bool] = {
            "id": db_user.id,
            "deleted": db_user.deleted,
        }
        return response_data


@router.post("/admin-grant", response_model=user_schema.UserAdminGrantResponse)
async def admin_grant(
    permission: user_schema.UserAdminGrant,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Creates a new permission

    Parameters
    ----------
        permission - permission input data

    Returns
    -------
        the new permission
    """

    # NOTE: if we ever want to change admin group, there is a helpful constant
    ADMIN_GROUP = AuthRole.SCHEMA_EDITOR

    # Helpers

    async def find_admin_group(role: AuthRole, session: AsyncSession) -> Group:
        group_select = select(Group).where(Group.name == role)
        admin_group = await session.execute(group_select)
        group_result = admin_group.unique().scalar_one_or_none()
        if not group_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"group_id": ErrorMessage.GROUP_NOT_FOUND_MESSAGE},
            )
        return group_result

    def check_already_admin(
        admin_group_id: int,
        user: User,
    ) -> None:
        if len(user.groups) > 0:
            first_group = user.groups[0]
            if first_group.id == admin_group_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"email": "User already has admin access"},
                )

    def set_user_group(user: User, group: Group) -> User:
        if user.groups:
            user.groups[0] = group
        else:
            user.groups.append(group)
        return user

    def check_email_domain(user: User) -> None:
        if not user.email.endswith("@nzdpu.com"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "email": "Can't grant access, user is not a nzdpu user."
                },
            )

    # Main handler

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        updated_user_ids = []

        # Get user
        result = await _session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.email == permission.email)
        )
        user = result.scalars().first()

        if user:
            # Check that user is not admin already
            check_email_domain(user)
            try:
                admin_group = await find_admin_group(ADMIN_GROUP, _session)
                check_already_admin(admin_group.id, user)
            except HTTPException as exc:
                raise exc

            user = set_user_group(user, admin_group)
            _session.add(user)
            await _session.commit()
            updated_user_ids.append(user.id)

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "email": "There is no registered user with this email address."
                },
            )

    response = {"user_id": updated_user_ids, "role": ADMIN_GROUP}
    return response


@router.post("/admin-revoke", response_model=user_schema.AdminRevokeResponse)
async def admin_revoke(
    permission: user_schema.AdminRevokeRequest,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    this fucntion revoke users from admin role
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        for us_id in permission.user_id:
            user = await load_user(user_id=us_id, session=_session)

            # Commit the changes to the user
            if user:
                await _session.execute(
                    user_group.update()
                    .where(user_group.c.user_id == us_id)
                    .values(group_id=3)
                )
                await _session.commit()

            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "user": f"provided user not exist with id  {us_id}"
                    },
                )

        return {"success": True}


def get_domain_from_email(email):
    # Split the email address at the "@" symbol
    parts = email.split("@")

    # Check if there are exactly two parts (username and domain)
    if len(parts) == 2:
        return parts[1]  # The second part is the domain
    return None  # Invalid email format
