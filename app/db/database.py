"""Database"""

import enum
from asyncio import current_task
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.dialects.postgresql.base import PGDDLCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql.ddl import DropTable

from app import settings
from app.loggers import get_nzdpu_logger

logger = get_nzdpu_logger()


class DBHost(str, enum.Enum):
    LEADER = "leader"
    FOLLOWER = "follower"


leader_engine = create_async_engine(
    settings.db.main.uri,
    max_overflow=15,
    pool_size=35,
    connect_args={"timeout": 120.0},
    **settings.db.main.sqla_extra,
)
follower_engines = (
    [create_async_engine(s.uri) for s in settings.db.secondary]
    if settings.db.secondary
    else None
)

sync_maker = sessionmaker()

common_session_params = {
    "autocommit": False,
    "autoflush": False,
    "expire_on_commit": False,
    "sync_session_class": sync_maker,
}


def get_sessionmaker(**kwargs) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker[AsyncSession](**kwargs)


def _get_current_task_id() -> int:
    return id(current_task())


sessionmakers = {
    DBHost.LEADER: async_sessionmaker[AsyncSession](
        bind=leader_engine, **common_session_params
    ),
}


class DBManager:
    def __init__(self, host: DBHost = DBHost.LEADER):
        self.host = host
        self.scoped_session = async_scoped_session(
            session_factory=sessionmakers[host],
            scopefunc=_get_current_task_id,
        )

    def get_session(self) -> AsyncSession:
        session = self.scoped_session()
        logger.debug(f"Spawning session {id(session)}")
        return session


@event.listens_for(leader_engine.sync_engine, "before_cursor_execute")
def bef_exc(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(perf_counter())


#
# # base class for DB models
# class Base(AsyncAttrs, DeclarativeBase):
#     pass

Base = declarative_base()


@compiles(DropTable, "postgresql")
def _compile_drop_table(element: DropTable, compiler: PGDDLCompiler) -> str:
    """
    A custom compiler for DropTable that applies to PostgreSQL
    """

    return compiler.visit_drop_table(element) + " CASCADE"
