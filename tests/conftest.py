"""Unit testing configuration"""

import asyncio
from asyncio import current_task
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator

import aiofiles
import nest_asyncio
import pytest
import pytest_asyncio
from aiodocker import Docker
from httpx import ASGITransport, AsyncClient, delete
from pytest import FixtureRequest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    close_all_sessions,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

import app.settings as settings
from app.db.database import Base, DBManager, logger
from app.db.extensions import create_postgres_extensions
from app.db.models import (
    Config,
)
from app.db.redis import RedisClient
from app.db.types import CompositeTypeInjector
from app.dependencies import (
    get_cache,
    get_db_manager,
    get_static_cache,
)
from app.main import app
from app.service.core.cache import CoreMemoryCache
from app.settings import DEFAULT_SA_ENGINE_OPTIONS
from cli.manage_db import get_init_config

nest_asyncio.apply()

"""
Pytest config section
"""


def pytest_collection_modifyitems(items) -> None:
    pytest_asyncio_tests = (
        item for item in items if pytest_asyncio.is_async_test(item)
    )
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="function")
def depends_on_firebase(request: FixtureRequest) -> bool:
    return "firebase" in request.keywords


@pytest_asyncio.fixture(scope="function", autouse=True)
async def firebase_guard(request: FixtureRequest, depends_on_firebase):
    """
    Autouse fixture only for tests involving firebase auth emulator:
     - ensures guard for FB_AUTH_EMULATOR_HOST environment
        variable not set (tests would run against production otherwise);
     - clears firebase users after each test.

    Use decorator @pytest.mark.firebase in test function to call this
    fixture.
    """
    if request.fixturename == "firebase_guard":
        if depends_on_firebase:
            request.getfixturevalue("firebase_emulator")
            yield
            # delete users after every firebase test
            project_id = settings.gcp.project
            delete(
                url=f"http://localhost:9099/emulator/v1/projects/{project_id}/accounts"
            )
        else:
            # do nothing
            yield


def pytest_addoption(parser):
    """
    Add Option
    -------

    """
    parser.addoption(
        "--firebase",
        action="store_true",
        dest="firebase",
        default=False,
        help="enable Firebase Auth Emulator tests",
    )


"""
Docker config section
"""


async def fill_docker_env(path: Path, service_config: dict) -> None:
    async with aiofiles.open(path, mode="r") as f:
        contents = await f.read()
        for line in contents.split("\n"):
            if "=" in line:
                line_no_space = line.strip()
                if line_no_space and not any(
                    line_no_space.startswith(char) for char in ("#", ";")
                ):
                    key, value = line_no_space.split("=", 1)
                    service_config["Env"].append(f"{key}={value}")


@asynccontextmanager
async def container_lifespan(
    docker_env_path: Path, volume_name: str, service_config: dict
) -> AsyncGenerator:
    docker = Docker()
    volumes = await docker.volumes.list()

    if volume_name not in [v["Name"] for v in volumes["Volumes"]]:
        await docker.volumes.create({"Name": volume_name})

    await fill_docker_env(docker_env_path, service_config)
    container = await docker.containers.create(config=service_config)
    await container.start()

    while True:
        container_info = await container.show()
        if container_info["State"]["Health"]["Status"] == "healthy":
            break
        await asyncio.sleep(1)

    yield

    await container.stop()
    await container.delete()
    if volume_name:
        volume = await docker.volumes.get(volume_name)
        if volume:
            await volume.delete()
    await docker.close()


@pytest_asyncio.fixture(scope="session")
async def firebase_config(pytestconfig) -> dict:
    firebase_config_path = pytestconfig.rootpath / "tests/firebase.json"
    return {
        "Image": "spine3/firebase-emulator",
        "Name": "firebase_auth_emulator",
        "Env": ["GCP_PROJECT=nzdpu-demo"],
        "HostConfig": {
            "PortBindings": {
                "9099/tcp": [
                    {"HostIp": "0.0.0.0", "HostPort": "9099"}
                ],  # Auth
                "8080/tcp": [
                    {"HostIp": "0.0.0.0", "HostPort": "8080"}
                ],  # Firestore
                "9000/tcp": [
                    {"HostIp": "0.0.0.0", "HostPort": "9000"}
                ],  # Realtime Database
                "9199/tcp": [
                    {"HostIp": "0.0.0.0", "HostPort": "9199"}
                ],  # Storage
            },
            "Binds": [
                f"{firebase_config_path.resolve().as_posix()}:/firebase/firebase.json"
            ],
        },
        "ExposedPorts": {
            "9099/tcp": {},
            "4000/tcp": {},
        },
        "Healthcheck": {
            "Test": [
                "CMD-SHELL",
                "wget --no-verbose --tries=1 --spider http://0.0.0.0:9099/emulator/v1/projects/nzdpu-demo/config || exit 1",
            ],
            "Interval": 2000000000,  # 2 seconds in nanoseconds
            "Timeout": 1000000000,  # 1 second in nanoseconds
            "Retries": 20,
        },
    }


@pytest_asyncio.fixture(scope="session")
async def postgres_config(pytestconfig) -> dict:
    init_script_path = (
        pytestconfig.rootpath
        / "resources/docker/test/db/docker-entrypoint-initdb.d/01-init-db.sh"
    )

    binds = SimpleNamespace(
        db_data="nzdpu_test_db:/var/lib/postgresql/data/",
        init_script=(
            f"{init_script_path.resolve().as_posix()}:"
            "/docker-entrypoint-initdb.d/01-init-db.sh"
        ),
    )

    return {
        "Image": "postgres:16.4",
        "Name": "nzdpu_test_db",
        "Env": [],
        "HostConfig": {
            "PortBindings": {"5432/tcp": [{"HostPort": "6432"}]},
            "Binds": [binds.db_data, binds.init_script],
        },
        "Healthcheck": {
            "Test": [
                "CMD-SHELL",
                "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}",
            ],
            "Interval": 5000000000,  # 5 seconds in nanoseconds
            "Timeout": 10000000000,  # 10 seconds in nanoseconds
            "Retries": 10,
        },
    }


@pytest_asyncio.fixture(scope="session")
async def docker_env_path(pytestconfig) -> Path:
    return pytestconfig.rootpath / "resources/docker/docker.env"


@pytest_asyncio.fixture(scope="session")
async def firebase_emulator(
    docker_env_path, firebase_config
) -> AsyncGenerator[None, None]:
    volume_name = "nzdpu_test_firebase"
    async with container_lifespan(
        docker_env_path, volume_name, firebase_config
    ):
        yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def postgres_db(
    docker_env_path, postgres_config
) -> AsyncGenerator[None, None]:
    volume_name = "nzdpu_test_db"
    async with container_lifespan(
        docker_env_path, volume_name, postgres_config
    ):
        yield


"""
SQLAlchemy test configuration
"""


@pytest_asyncio.fixture(scope="session")
async def sqla_engine() -> AsyncEngine:
    return create_async_engine(
        settings.db.test.postgres.uri, **DEFAULT_SA_ENGINE_OPTIONS
    )


@pytest_asyncio.fixture(scope="session")
async def sqla_conn(
    sqla_engine: AsyncEngine,
) -> AsyncConnection:
    conn = sqla_engine.connect()
    yield await conn.start()
    await conn.close()


async def setup_types_and_ext(
    sqla_conn: AsyncConnection,
) -> None:
    injector = CompositeTypeInjector(sqla_conn)
    try:
        await injector.create_composite_types_in_postgres()
        await injector.inject_composite_types()
        await create_postgres_extensions(sqla_conn)
    except Exception as exc:
        raise exc


async def setup_tables(
    sqla_conn: AsyncConnection,
) -> None:
    await sqla_conn.run_sync(Base.metadata.reflect)
    wis_tables = [
        table
        for table in Base.metadata.tables.values()
        if table.name.startswith("wis")
    ]

    await sqla_conn.run_sync(Base.metadata.drop_all)
    await sqla_conn.run_sync(Base.metadata.create_all, tables=wis_tables)
    await sqla_conn.run_sync(Base.metadata.reflect)


@pytest_asyncio.fixture(scope="function", name="session", autouse=True)
async def sqla_session(sqla_engine, sqla_conn) -> AsyncSession:
    """
    Create a database session for testing
    """

    await setup_tables(sqla_conn)
    await setup_types_and_ext(sqla_conn)

    engine = sqla_engine

    async_session_factory = async_sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
        sync_session_class=sessionmaker(),
    )

    def _get_current_task_id() -> int:
        return id(current_task())

    class TestDBManager(DBManager):
        def __init__(self):
            self.scoped_session_factory = async_scoped_session(
                session_factory=async_session_factory,
                scopefunc=_get_current_task_id,
            )

        def get_session(self):
            session = self.scoped_session_factory()
            logger.debug(f"Spawning session {id(session)}")
            return session

    async def test_get_session() -> AsyncGenerator[DBManager, None]:
        db_manager = TestDBManager()
        try:
            yield db_manager
        except SQLAlchemyError:
            await db_manager.scoped_session_factory.rollback()
        finally:
            await db_manager.scoped_session_factory.rollback()
            await db_manager.scoped_session_factory.close_all()
            await close_all_sessions()

    app.dependency_overrides[get_db_manager] = test_get_session
    db_manager = TestDBManager()

    yield db_manager.get_session()
    app.dependency_overrides.clear()
    await close_all_sessions()


"""
WIS app fixtures
"""


@pytest_asyncio.fixture(name="client", scope="session")
async def async_client_fixture():
    """
    Create a test client
    """

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://tests"
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture()
async def static_cache(session):
    cache = CoreMemoryCache(session)
    await cache.load_data()

    async def test_get_static_cache():
        yield cache

    app.dependency_overrides[get_static_cache] = test_get_static_cache
    yield cache


@pytest_asyncio.fixture(scope="function")
async def config(session):
    existing_config_properties = (await session.scalars(select(Config))).all()
    if not existing_config_properties:
        init_config = get_init_config()
        for config_entry in init_config:
            config_model = Config(
                name=config_entry.name,
                type=config_entry.type,
                value=config_entry.value,
                description=config_entry.description,
            )
            session.add(config_model)

        await session.commit()


@pytest_asyncio.fixture(name="redis_client", scope="function")
async def redis_client():
    """
    Create a test Redis client.
    """
    test_client = RedisClient(
        host=settings.cache.host,
        port=settings.cache.port,
        password=settings.cache.password,
        db=1,
    )

    test_client.key_prefix = "test:"

    async def test_get_cache():
        yield test_client

    app.dependency_overrides[get_cache] = test_get_cache

    yield test_client
    await test_client.flushdb()
