"""Utility functions"""

import json
import os
import unicodedata
from datetime import datetime

import jwt
from fastapi import HTTPException, status
from jsonschema.validators import RefResolver
from jwt import DecodeError, ExpiredSignatureError, PyJWTError
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from sqlalchemy import Connection, Table, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload

from app import settings
from app.db.database import Base
from app.db.models import AuthMode, User
from app.schemas.token import (
    AccessTokenData,
    RefreshTokenData,
    TokenValidationErrorEnum,
)

# pylint: disable = unsupported-binary-operation

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LocalTokenVerificationError(Exception):
    """Custom exception for locally generated token verification errors"""

    def __init__(self, code: TokenValidationErrorEnum):
        """
        Inits the instance of this class.
        """
        self.code = code


def encrypt_password(pwd: str):
    """
    Encrypt a password for database storage. Auto-generates the salt and encrypts it into the hash.
    :param pwd: the clear password to encrypt
    :return: the encrypted password
    """
    return pwd_context.hash(pwd)


def check_password(pwd: str, hashed_pwd):
    """
    Check encrypted password
    :param pwd: the clear password to check
    :param hashed_pwd: the hashed password to check against
    :return: true if the passwords match, false otherwise
    """

    try:
        valid = pwd_context.verify(pwd, hashed_pwd)
    except UnknownHashError:
        valid = False

    return valid


def create_access_token(data: AccessTokenData):
    """
    Creates an access token for JWT authentication
    :param data: token data
    """
    encoded_jwt = jwt.encode(
        payload=data.model_dump(),
        key=settings.jwt.secret.get_secret_value(),
        algorithm=settings.jwt.hash_algorithm,
    )
    return encoded_jwt


def create_refresh_token(data: RefreshTokenData) -> str:
    """
    Generates a refresh token.

    Args:
        data (RefreshTokenData): The token data.

    Returns:
        str: The JWT encoded refresh token.
    """

    return jwt.encode(
        payload=data.model_dump(),
        key=settings.jwt.secret.get_secret_value(),
        algorithm=settings.jwt.hash_algorithm,
    )


async def verify_local_token(token: str, session: AsyncSession) -> User | None:
    """
    Verifies a locally generated token
    :param token: access token
    :return: user information or relevant data from the token
    """
    try:
        decoded_token = jwt.decode(
            token,
            key=settings.jwt.secret.get_secret_value(),
            algorithms=[settings.jwt.hash_algorithm],
        )
    except DecodeError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.INVALID_SIGNATURE
        ) from ex
    except ExpiredSignatureError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.EXPIRED
        ) from ex
    except PyJWTError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.VERIFICATION_FAILED
        ) from ex

    user = await session.scalar(
        select(User)
        .options(selectinload(User.groups))
        .where(User.name == decoded_token["sub"])
    )
    if not user:
        return None
    iat = datetime.fromtimestamp(decoded_token["iat"])
    if user.token_iat != iat:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"token": "Invalid token"},
        )
    return user


async def verify_refresh_token(rtoken: str, session: AsyncSession):
    try:
        decoded_token = jwt.decode(
            rtoken,
            key=settings.jwt.secret.get_secret_value(),
            algorithms=[settings.jwt.hash_algorithm],
        )
        token_data = RefreshTokenData(**decoded_token)
    except DecodeError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.INVALID_SIGNATURE
        ) from ex
    except ExpiredSignatureError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.EXPIRED
        ) from ex
    except PyJWTError as ex:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.VERIFICATION_FAILED
        ) from ex

    # verify token content
    user = await session.scalar(
        select(User).where(User.name == token_data.sub)
    )
    if not user:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.USER_NOT_FOUND
        )

    if token_data.uid != user.refresh_token_uid:
        raise LocalTokenVerificationError(
            code=TokenValidationErrorEnum.INVALID
        )

    return user


def is_local_token(token: str) -> bool:
    """
    Checks if the token is locally generated
    :param token: access token
    :return: True if the token is locally generated, False otherwise
    """
    try:
        decoded_token = jwt.decode(
            token,
            settings.jwt.secret.get_secret_value(),
            algorithms=[settings.jwt.hash_algorithm],
        )
        token_type = decoded_token.get("auth_mode")
        return token_type == AuthMode.LOCAL
    except jwt.PyJWTError:
        return False


def load_json_schema(name: str):
    """
    Return a JSON schema, along with the corresponding path resolver
    :param name: the schema name, without the extension
    :return: the (schema, resolver) couple
    """

    schema_root: str = "resources/json-schema"

    # load label schema
    with open(
        os.path.join(settings.BASE_DIR, f"../{schema_root}/{name}.json"),
        encoding="utf-8",
    ) as f_schema:
        schema = json.load(f_schema)

    # create path resolver for schema
    resolver = RefResolver(
        f"file://{settings.BASE_DIR}/../{schema_root}/", schema
    )

    return schema, resolver


async def increment_login_attempts_and_get_error_message(
    user: User,
    session: AsyncSession,
    firebase_user: bool = False,
    blocked_by_firebase: bool = False,
):
    # Increment failed login attempts for both user types.
    if user.failed_login_attempts is None:
        user.failed_login_attempts = 0
    user.failed_login_attempts += 1
    await session.commit()

    error_message = {
        "password": "Incorrect email or password. Please try again or reset your password."
    }

    # Firebase users are blocked by Firebase, so we check if it's blocked and return appropriate message.
    if firebase_user:
        if blocked_by_firebase:
            error_message = {
                "password": (
                    "Your account has been temporarily locked due to too many failed login attempts. "
                    "Please try again later, or reset your password."
                ),
                "disable_login": True,
            }

        return error_message

    # Local users are blocked in our database.
    if (
        user.failed_login_attempts
        >= settings.application.password_max_login_attempts
    ):
        user.enabled = False
        await session.commit()

        error_message = {
            "password": (
                "Your account has been temporarily locked due to too many failed login attempts. "
                "Please try again later, or reset your password."
            ),
            "disable_login": True,
        }

    return error_message


def get_url_from_session(session: AsyncSession):
    """
    Get currently used engine url

    Parameters
    ----------
    session - database session

    Returns
    -------
    current engine url
    """
    return session.get_bind().engine.url


def get_engine_from_session(session: AsyncSession):
    """
    Get currently used engine

    Parameters
    ----------
    session - database session

    Returns
    -------
    current engine
    """
    # get currently used engine url
    engine_url = get_url_from_session(session)
    # create engine
    engine = create_async_engine(engine_url)

    return engine


async def reflect_form_table(
    session: AsyncSession, form_table: str = "nzdpu_form"
) -> Table:
    def inspect_table(conn: Connection):
        return Table(form_table, Base.metadata, autoload_with=conn)

    engine = get_engine_from_session(session)

    async with engine.begin() as conn:
        table = await conn.run_sync(inspect_table)

    return table


# fix TypeError: Dict key must be str
def convert_keys_to_str(d):
    if isinstance(d, dict):
        return {str(k): convert_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_keys_to_str(i) for i in d]
    else:
        return d


def convert_datetimes(data):
    if isinstance(data, dict):
        return {k: convert_datetimes(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_datetimes(i) for i in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data


def normalize_datetime(dt_str):
    """Normalize datetime strings to a standard format."""
    try:
        # Attempt to parse the datetime string with known formats
        if "T" in dt_str:
            return datetime.fromisoformat(dt_str)
        else:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        # Return the original string if it can't be parsed as a datetime
        return dt_str


def sanitize_filename(**fragments: str) -> str:
    path = ""
    for fragment in fragments.values():
        for word in fragment.split(" "):
            word = "".join(c for c in word.lower() if c.isalnum())
            path += (
                unicodedata.normalize("NFKD", f"{word}_")
                .encode("ascii", "ignore")
                .decode("ascii")
            )
    return path[:-1]


def excel_filename_sics(exclude_classification_forced: bool | None) -> str:
    if exclude_classification_forced == False:
        return "_with_sics"

    return ""
