"""Main App"""

from contextlib import asynccontextmanager
from datetime import datetime
from time import perf_counter
from typing import Annotated, Any, AsyncGenerator, Dict
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.database import DBManager
from app.schemas.validation_exception_handler import (
    validation_exception_handler,
)
from app.service.core.cache import CoreMemoryCache
from app.service.firebase_rest_api_client import (
    FirebaseRESTAPIClient,
    FirebaseRESTAPIClientException,
    UnhandledFirebaseRESTAPIClientException,
)

from . import settings
from .api_specs_utils import RouteViewer
from .constraint_validator import ConstraintValidationException
from .db.extensions import create_postgres_extensions
from .db.models import (
    AuthMode,
    User,
)
from .db.types import CompositeTypeInjector, NullTypeState
from .dependencies import (
    DbManager,
    get_current_user_or_none,
    initialize_firebase_rest_api_client,
)
from .loggers import get_nzdpu_logger
from .routers import (
    attribute_views,
    attributes,
    auth_router,
    choices,
    companies,
    config,
    managed_files,
    metrics,
    prompts,
    public_router,
    schema,
    search,
    submissions_router,
    system,
    tables,
    vaults,
    views,
)
from .routers.external import organizations
from .schemas.token import (
    AccessTokenData,
    RefreshTokenData,
    RefreshTokenRequest,
    Token,
    TokenValidationErrorEnum,
)
from .utils import (
    LocalTokenVerificationError,
    check_password,
    create_access_token,
    create_refresh_token,
    increment_login_attempts_and_get_error_message,
    verify_refresh_token,
)

settings.setup_logging()
logger = get_nzdpu_logger()


@asynccontextmanager
async def application_startup_handler(
    app: FastAPI,
) -> AsyncGenerator[None, None]:
    """
    Context manager to get the cache object.
    """
    pg_settings = settings.db.main
    assert pg_settings.uri is not None

    db_manager = DBManager()

    async with db_manager.get_session() as session:
        try:
            async with CompositeTypeInjector.from_session(session) as injector:
                await injector.create_composite_types_in_postgres()
                await injector.inject_composite_types()
                await create_postgres_extensions(session)
        except Exception as e:
            raise e

        static_cache = CoreMemoryCache(session)
        await static_cache.load_data()

        app.state.static_cache = static_cache

    yield

    if hasattr(app.state, "redis_client"):  # type: ignore
        await app.state.redis_client.disconnect()  # type: ignore


# create main app
app = FastAPI(
    title=f"{settings.SERVICE_NAME} - API",
    version=settings.SERVICE_API_VERSION,
    docs_url=None,
    redoc_url=None,
    description="The API exposed by the WIS component of NZDPU",
    lifespan=application_startup_handler,
    terms_of_service="",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    openapi_url=None,
    separate_input_output_schemas=False,
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Middleware to log request response time.
    """
    s = perf_counter()
    response = await call_next(request)
    logger.info(f"Request {request.url} response time: {perf_counter() - s}")
    return response


# Add CORS Middleware
app.add_middleware(CORSMiddleware, **settings.CORSSettings().model_dump())

# Add GZIP Middleware
app.add_middleware(GZipMiddleware, minimum_size=settings.GZIP_MIN_SIZE)
app.add_exception_handler(ValidationError, validation_exception_handler)


# this is need it to send up the null type as an array for FE typings
def add_null_types_to_open_api_specification(openapi_schema: Dict[str, Any]):
    null_types_array_schema = {
        "type": "array",
        "items": {"type": "string", "enum": NullTypeState.values()},
        "example": NullTypeState.values(),
    }
    if "components" not in openapi_schema:
        openapi_schema["components"] = {"schemas": {}}
    openapi_schema["components"]["schemas"]["NullTypesArray"] = (
        null_types_array_schema
    )

    return openapi_schema


@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_spec(x_api_key: Annotated[str | None, Header()] = None):
    if settings.application.show_api_docs or (
        x_api_key == settings.application.system_api_key
    ):
        return add_null_types_to_open_api_specification(
            get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                contact=app.contact,
                license_info=app.license_info,
                routes=app.routes,
            )
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "global": "You are not authorized to see the OpenAPI specification."
        },
    )


@app.get("/docs", include_in_schema=False)
async def get_api_docs(x_api_key: Annotated[str | None, Header()] = None):
    if settings.application.show_api_docs or (
        x_api_key == settings.application.system_api_key
    ):
        return get_swagger_ui_html(
            openapi_url="/openapi.json", title=app.title
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"global": "You are not authorized to see the API docs."},
    )


@system.router.get("/api/specs", include_in_schema=False)
async def openapi(user: User | None = Depends(get_current_user_or_none)):
    route_viewer = RouteViewer(app=app, user=user)

    try:
        routes = route_viewer.get_user_routes()
    except FirebaseRESTAPIClientException as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc

    return add_null_types_to_open_api_specification(
        get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            contact=app.contact,
            license_info=app.license_info,
            routes=routes,
        )
    )


app.include_router(attributes.router)
app.include_router(attribute_views.router)
app.include_router(auth_router)
app.include_router(choices.router)
app.include_router(prompts.router)
app.include_router(submissions_router)
app.include_router(tables.router)
app.include_router(views.router)
app.include_router(vaults.router)
app.include_router(managed_files.router)
app.include_router(public_router)
app.include_router(organizations.router)
app.include_router(schema.router)
app.include_router(search.router)
app.include_router(companies.router)
app.include_router(config.router)
app.include_router(system.router)
app.include_router(metrics.router)


@app.post("/token", response_model=Token)
async def token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db_manager: DbManager,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
):
    """Authenticate user and generates an authentication token on success"""
    # load user from database
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        username = form_data.username.lower()
        stmt = select(User).where(
            (User.email == username) | (User.name == username)
        )
        result = await _session.execute(stmt)
        user: User = result.scalars().first()

        # init always True, only change for Firebase users
        email_verified = True

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "username": (
                        "Incorrect email or password. Please try again or"
                        " reset your password."
                    ),
                    "email": (
                        "Incorrect email or password. Please try again or"
                        " reset your password."
                    ),
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.enabled is False:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "password": (
                        "Your account has been temporarily locked due to too many failed login attempts. "
                        "Please try again later, or reset your password."
                    ),
                    "disable_login": True,
                },
            )

        if user.auth_mode == AuthMode.LOCAL:
            # check user password
            valid = check_password(form_data.password, user.password)
            if not valid:
                error_message = (
                    await increment_login_attempts_and_get_error_message(
                        user=user, session=_session
                    )
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=error_message,
                    headers={"WWW-Authenticate": "Bearer"},
                )

            iat = datetime.utcnow()
            exp = iat + settings.jwt.access_exp_delta
            r_exp = iat + settings.jwt.refresh_exp_delta

            access_token = create_access_token(
                data=AccessTokenData(sub=user.name, iat=iat, exp=exp)
            )
            # reset failed login attempts on successful login
            user.failed_login_attempts = 0
            # set the last_access field to now
            user.last_access = datetime.utcnow()
            # save UID for refresh token
            user.refresh_token_uid = str(uuid4())
            # save token iat for verification
            user.token_iat = datetime.fromtimestamp(
                jwt.decode(access_token, options={"verify_signature": False})[
                    "iat"
                ]
            )
            _session.add(user)
            refresh_token = create_refresh_token(
                data=RefreshTokenData(
                    sub=user.name,
                    uid=user.refresh_token_uid,
                    iat=iat,
                    exp=r_exp,
                )
            )

        elif user.auth_mode == AuthMode.FIREBASE:
            if not user.email:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "user.email": (
                            "User does not have an email address in the"
                            " system."
                        )
                    },
                )
            try:
                fb_user = pb.sign_in_with_email_and_password(
                    email=user.email,
                    password=form_data.password,  # type: ignore
                )
            except FirebaseRESTAPIClientException as exc:
                if "password" in exc.detail:
                    blocked_by_firebase = exc.detail.get(
                        "blocked_by_firebase", False
                    )

                    error_message = (
                        await increment_login_attempts_and_get_error_message(
                            user=user,
                            session=_session,
                            firebase_user=True,
                            blocked_by_firebase=blocked_by_firebase,
                        )
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=error_message,
                        headers={"WWW-Authenticate": "Bearer"},
                    ) from exc
                raise
            else:
                access_token = fb_user.id_token
                fb_user_info = pb.get_account_info(token=access_token)
                email_verified = fb_user_info.users[0].email_verified
                user.token_iat = datetime.fromtimestamp(
                    jwt.decode(
                        access_token, options={"verify_signature": False}
                    )["iat"]
                )
                refresh_token = fb_user.refresh_token

                # Reset failed login attempts on successful login
                user.failed_login_attempts = 0
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"global": "Unknown auth mode"},
            )

        user.email_verified = email_verified
        _session.add(user)
        await _session.commit()

        # block log in if email not verified
        if not email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "email": (
                        "You need to verify your email before being able to"
                        " log in. Please check your associated email for the"
                        " verification link."
                    ),
                    "email_verified": False,
                },
            )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            email_verified=email_verified,
        )


@app.post("/token/refresh", response_model=Token)
async def refresh_token(
    db_manager: DbManager,
    data: RefreshTokenRequest,
    pb: FirebaseRESTAPIClient = Depends(initialize_firebase_rest_api_client),
) -> Token:
    """
    Generate a new access token using the refresh token of a user.

    Args:
        data (RefreshTokenRequest): The request payload containing the
            refresh token

    Returns:
        Token: A new access token for the authenticated user.
    """

    _session: AsyncSession
    # FIREBASE USERS FIRST
    try:
        response = pb.get_id_token_from_refresh_token(
            refresh_token=data.refresh_token
        )
    except FirebaseRESTAPIClientException as exc:
        # probably not a Firebase refresh token? pass for now and
        # perform check for local refresh token
        logger.debug(f"Failed refresh token for Firebase: {exc.detail}")
    else:
        access_token = response["id_token"]
        refresh_token = response["refresh_token"]
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        async with db_manager.get_session() as _session:
            user = await _session.scalar(
                select(User).where(User.email == decoded["email"])
            )
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"global": "User not found."},
                )
            user.token_iat = datetime.fromtimestamp(decoded["iat"])
            _session.add(user)
            await _session.commit()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            email_verified=user.email_verified,
        )
    # LOCAL USERS
    async with db_manager.get_session() as _session:
        user = await verify_refresh_token(data.refresh_token, _session)
        # store new refresh token UID
        user.refresh_token_uid = str(uuid4())
        _session.add(user)
        await _session.commit()

        iat = datetime.utcnow()
        exp = iat + settings.jwt.access_exp_delta

        access_token = create_access_token(
            data=AccessTokenData(sub=user.name, iat=iat, exp=exp)
        )
        user.token_iat = datetime.fromtimestamp(
            jwt.decode(access_token, options={"verify_signature": False})[
                "iat"
            ]
        )
        _session.add(user)
        await _session.commit()

        r_exp = iat + settings.jwt.refresh_exp_delta
        refresh_token = create_refresh_token(
            data=RefreshTokenData(
                sub=user.name, uid=user.refresh_token_uid, iat=iat, exp=r_exp
            )
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            email_verified=user.email_verified,
        )


@app.exception_handler(ConstraintValidationException)
async def constaint_validator_exception_handler(
    request: Request, exc: ConstraintValidationException
):
    """
    Exception handler for constraints validation errors.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "reason": "Constraints validation error.",
            "msg": exc.message,
            "loc": exc.column_name,
            "value": exc.value,
            "constraint_condition": exc.condition,
            "constraint_action": exc.action,
            "detail": {exc.column_name: exc.condition},
        },
    )


@app.exception_handler(UnhandledFirebaseRESTAPIClientException)
async def unhandled_firebase_rest_api_client_exception_handler(
    request: Request, exc: UnhandledFirebaseRESTAPIClientException
):
    """
    Exception handler for unhandled Firebase REST API errors.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "reason": "Firebase REST API exception",
            "msg": exc.message,
            "url": exc.url,
        },
    )


@app.exception_handler(FirebaseRESTAPIClientException)
async def firebase_rest_api_client_exception_handler(
    request: Request, exc: FirebaseRESTAPIClientException
):
    """
    Exception handler for Firebase REST API errors.
    """
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}
    )


@app.exception_handler(LocalTokenVerificationError)
async def token_verification_exception_handler(
    request: Request, exc: LocalTokenVerificationError
):
    """
    Exception handler for token validation errors.
    """
    match exc.code:
        case TokenValidationErrorEnum.INVALID:
            message = "Token is invalid."
        case TokenValidationErrorEnum.INVALID_SIGNATURE:
            message = "The token signature is invalid."
        case TokenValidationErrorEnum.EXPIRED:
            message = "Token has expired."
        case TokenValidationErrorEnum.USER_NOT_FOUND:
            message = (
                "The user corresponding to the refresh token was not found"
            )
        case TokenValidationErrorEnum.VERIFICATION_FAILED:
            message = "Token signature verification failed."
        case _:
            message = "The token validation failed for unknown reasons."
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": {"token": message}},
    )
