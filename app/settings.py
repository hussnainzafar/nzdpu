"""Default configuration settings"""

from __future__ import annotations

import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Sequence

import structlog
from dotenv import load_dotenv
from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FilePath,
    SecretStr,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from typing_extensions import Self

load_dotenv()

# general
BASE_DIR = Path(__file__).resolve(strict=True).parent
local_dotenv_path = BASE_DIR.parent / ".env"

SERVICE_CODE = "nzdpu-wis"
SERVICE_NAME = "NZDPU: Web Interview System"
SERVICE_VERSION = "1.8.22"
SERVICE_API_VERSION = "1.8.22"
GZIP_MIN_SIZE = 102400  # minimum size in bytes to return gzip payoad
DEFAULT_SA_ENGINE_OPTIONS = {"future": True, "pool_pre_ping": True}


class AppSettings(BaseSettings):
    """
    App configuration
    """

    password_max_login_attempts: Annotated[
        int,
        Field(default=10, description="Setting to control max login attempts"),
    ]
    show_api_docs: Annotated[
        bool,
        Field(
            default=False, description="Control over showing api docs publicly"
        ),
    ]
    bypass_cors: Annotated[
        bool,
        Field(
            default=False, description="Bypass CORS. Useful for development"
        ),
    ]
    system_api_key: Annotated[
        str | None, Field(description="X-API-Key for auth", default=None)
    ]
    x_qa_key: Annotated[
        str | None, Field(default=None, description="Special auth key for QA")
    ]
    save_companies_files_to_bucket: Annotated[
        bool,
        Field(
            default=False,
            description="Flag that says if we will save the companies generated files to bucket via save_excel.py script",
        ),
    ]

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=local_dotenv_path, extra="allow"
    )


application = AppSettings()


class JWTSettings(BaseSettings):
    """
    JWT options
    """

    secret: Annotated[
        SecretStr | None,
        Field(default=None, description="Secret value for JWT encoding"),
    ]
    hash_algorithm: Annotated[
        str | None, Field(default="HS256", description="Hash algorithm")
    ]
    access_exp_delta: Annotated[
        timedelta,
        Field(
            default=timedelta(3600),
            description="Time to live for access token",
        ),
    ]
    refresh_exp_delta: Annotated[
        timedelta,
        Field(
            default=timedelta(days=1),
            description="Time to live for refresh token",
        ),
    ]

    model_config = SettingsConfigDict(
        env_prefix="JWT_", env_file=local_dotenv_path, extra="allow"
    )


jwt = JWTSettings()


def postgres_uri_factory(s: PostgresSettings):
    return URL.create(
        drivername=f"{s.proto}+{s.driver}" if s.driver else f"{s.proto}",
        username=s.user,
        password=s.password.get_secret_value() if s.password else "",
        host=s.host,
        port=s.port,
        database=s.database,
    ).render_as_string(hide_password=False)


class PostgresSettings(BaseModel):
    """
    Postgres configuration model
    """

    proto: Annotated[
        str, Field(default="postgresql", description="Postgres protocol")
    ]
    driver: Annotated[
        str, Field(default="asyncpg", description="Postgres driver")
    ]
    host: Annotated[
        str, Field(default="localhost", description="Postgres host")
    ]
    port: Annotated[int, Field(default=5432, description="Postgres port")]
    database: Annotated[
        str | None, Field(default=None, description="Postgres database")
    ]
    user: Annotated[
        str | None,
        Field(
            default=None,
            description="Postgres user",
        ),
    ]
    password: Annotated[
        SecretStr | None,
        Field(default=None, description="Postgres password"),
    ]
    uri: Annotated[str | None, Field(default=None, description="Postgres uri")]
    sqla_extra: Annotated[
        dict,
        Field(
            default=DEFAULT_SA_ENGINE_OPTIONS,
            description="Parameters for SQLAlchemy engine",
        ),
    ]

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    @model_validator(mode="after")
    def uri_from_attrs(self) -> Self:
        if not self.uri:
            try:
                self.uri = postgres_uri_factory(self)
            except ValidationError as e:
                raise e
        return self


def resolve_sqlite_path(value):
    try:
        # Determine the SQLite database path
        path = (BASE_DIR.parent / "tmp" / "test.db").resolve()

        # Create the necessary directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        # If the file does not exist, create it
        if not path.exists():
            path.touch()  # This creates the file

        return path
    except (RuntimeError, OSError) as exc:
        print(f"Error resolving SQLite path: {exc}")
        return None


class SQLiteSettings(BaseModel):
    """
    SQLite settings
    """

    proto: Annotated[str, Field(default="sqlite")]
    driver: Annotated[str, Field(default="aiosqlite")]
    database: Annotated[str, Field(default="test_db")]
    path: Annotated[FilePath, BeforeValidator(resolve_sqlite_path)]
    uri: Annotated[str | None, Field(default=None)]

    model_config = ConfigDict(extra="allow")

    def model_post_init(self, __context: Any) -> None:
        if not self.uri:
            try:
                self.uri = (
                    f"{self.proto}+{self.driver}:///{self.path.as_posix()}"
                )
            except ValidationError as e:
                raise e


class DBTestSettings(BaseModel):
    """
    Test database model
    """

    sqlite: Annotated[
        SQLiteSettings | None,
        Field(default=None, description="SQLite database settings"),
    ]
    postgres: Annotated[
        PostgresSettings | None,
        Field(default=None, description="Postgres database settings"),
    ]


class DBSettings(BaseSettings):
    """
    Database configuration
    """

    main: Annotated[
        PostgresSettings | None,
        Field(
            default=None, description="Main database settings. Postgres only"
        ),
    ]
    test: Annotated[
        DBTestSettings | None,
        Field(
            default=None,
            description="Test database settings. Can include SQLite and Postgres",
        ),
    ]
    secondary: Annotated[
        list[PostgresSettings] | None,
        Field(
            default=None,
            description="List containing settings for multiple secondary Postgres nodes",
        ),
    ]

    model_config = SettingsConfigDict(
        env_prefix="DB__",
        env_file=local_dotenv_path,
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="allow",
    )


db = DBSettings()


class GoogleCloudSettings(BaseSettings):
    """
    Google related settings
    """

    project: Annotated[
        str | None,
        Field(
            default=None,
            description="Google Cloud project ID",
            validation_alias=AliasChoices(
                "GCP_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"
            ),
        ),
    ]
    default_bucket: Annotated[
        str | None, Field(default=None, description="Default bucket name")
    ]
    default_service_account_email: Annotated[
        str | None,
        Field(default=None, description="Default service account email"),
    ]

    model_config = SettingsConfigDict(
        env_prefix="GCP_", env_file=local_dotenv_path, extra="allow"
    )


gcp = GoogleCloudSettings()


class FirebaseSettings(BaseSettings):
    """
    Firebase settings
    """

    api_key: Annotated[
        str | None, Field(default=None, description="Firebase API key")
    ]
    auth_emulator_host: Annotated[
        str | None,
        Field(
            default=None,
            description="Firebase auth emulator host. Do not use if emulator is not running",
        ),
    ]
    api_url: Annotated[
        str | None, Field(default=None, description="Firebase api url")
    ]

    model_config = SettingsConfigDict(
        env_prefix="FIREBASE_", env_file=local_dotenv_path, extra="allow"
    )

    def model_post_init(self, __context: Any) -> None:
        self.api_url = (
            "https://identitytoolkit.googleapis.com/v1"
            if not self.auth_emulator_host
            else f"http://{self.auth_emulator_host}/identitytoolkit.googleapis.com/v1"
        )


fb = FirebaseSettings()

cors_allow_settings = {
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

cors_restrict_settings = {
    "allow_origins": (),
    "allow_methods": ("GET", "OPTIONS"),
    "allow_headers": (),
}

get_env_cors_settings = (
    cors_allow_settings if application.bypass_cors else cors_restrict_settings
)


class CORSSettings(BaseSettings):
    """Allows control of the CORS middleware, mostly for the FE folk"""

    allow_origins: Annotated[
        Sequence[str], Field(default=get_env_cors_settings["allow_origins"])
    ]
    allow_methods: Annotated[
        Sequence[str], Field(default=get_env_cors_settings["allow_methods"])
    ]
    allow_headers: Annotated[
        Sequence[str], Field(default=get_env_cors_settings["allow_headers"])
    ]
    allow_credentials: Annotated[bool, Field(default=False)]
    expose_headers: Annotated[Sequence[str], Field(default_factory=list)]
    max_age: Annotated[int, Field(default=600)]
    allow_origin_regex: Annotated[str | None, Field(default=None)]


class RedisSettings(BaseSettings):
    """
    Redis cache settings
    """

    host: Annotated[str, Field(default="localhost")]
    port: Annotated[int, Field(default=6379)]
    ttl: Annotated[int, Field(default=3600 * 24 * 7)]  # seven days
    enabled: Annotated[int, Field(default=1)]
    password: Annotated[str | None, Field(default=None)]

    model_config = SettingsConfigDict(
        env_file=local_dotenv_path, env_prefix="REDIS_", extra="allow"
    )


cache = RedisSettings()  # type: ignore


# Logging
class LogSettings(BaseSettings):
    """
    Settings for loggers
    """

    nzdpu_log_level: int = logging.INFO  # main logger level
    sql_log_level: int = logging.INFO  # sql events log level


log = LogSettings()


def setup_logging():
    """
    Configures logging for the application using `structlog` and `logging`, ensuring all log levels
    (DEBUG, INFO, WARNING, ERROR) are captured and output in JSON format.
    This function:
    - Sets the standard logging configuration to capture logs at all levels by setting the level to DEBUG.
    - Configures `structlog` with processors to format logs, including:
      - Filtering by log level
      - Adding logger name and log level to the output
      - Adding timestamps in ISO format
      - Rendering stack information and exception details
      - Formatting logs as JSON
    - Ensures that all logs are output to `stdout` in a consistent format using `structlog` for structured logging.
    Usage:
        Call this function once at the start of your application to set up comprehensive logging.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    # Set up standard logging configuration to capture all levels, including DEBUG
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,  # Set to DEBUG to capture all log levels
    )
    # Redirect standard logging messages to structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,  # Filter by log level
            structlog.stdlib.add_logger_name,  # Add logger name to the log
            structlog.stdlib.add_log_level,  # Add log level to the log
            timestamper,  # Add timestamp
            structlog.processors.StackInfoRenderer(),  # Render stack info if available
            structlog.processors.format_exc_info,  # Format exception info if available
            structlog.processors.JSONRenderer(),  # Render logs as JSON
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    # Ensure all standard logging goes through structlog
    logging.getLogger().handlers.clear()
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
