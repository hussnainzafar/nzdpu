from __future__ import annotations

import warnings
from contextlib import asynccontextmanager
from enum import StrEnum
from types import SimpleNamespace
from typing import (
    Annotated,
    Any,
    Generic,
    Optional,
    Sequence,
    TypeVar,
)

from pydantic import BaseModel, Field
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.sql.type_api import UserDefinedType
from sqlalchemy.util import FacadeDict
from typing_extensions import Self

from app.db.database import Base
from app.loggers import get_nzdpu_logger
from app.schemas.enums import EnumValuesTrait

logger = get_nzdpu_logger()

"""
Custom types models, enums and other data
"""

T = TypeVar("T", int, str, float, bool, dict, None)
EN_DASH = "–"


class NullTypeState(EnumValuesTrait[str], StrEnum):
    DASH = "-"
    LONG_DASH = "—"
    NOT_APPLICABLE = "N/A"


class PostgresCustomType(StrEnum):
    INT_OR_NULL = "int_or_null"
    TEXT_OR_NULL = "text_or_null"
    FLOAT_OR_NULL = "float_or_null"
    FORM_OR_NULL = "form_or_null"
    BOOL_OR_NULL = "bool_or_null"
    FILE_OR_NULL = "file_or_null"
    NULL_TYPE_ENUM = "null_type_enum"


class CompositeAttribute(BaseModel, Generic[T]):
    """
    Abstract Pydantic representation for composite postgres type
    """

    value: Annotated[
        Optional[T],
        Field(
            default=None, description="Composite type item's value of type T"
        ),
    ]
    state: Annotated[
        Optional[NullTypeState],
        Field(
            default=None,
            description="State of the value. Can be either dash '-', long dash '—' or 'N/A'",
        ),
    ]

    def __composite_values__(
        self,
    ) -> tuple[Optional[T], Optional[NullTypeState]]:
        return self.value, self.state

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(value={self.value}, state={self.state})"


class BaseNullableType(UserDefinedType, Generic[T]):
    """
    SQLAlchemy custom type
    """

    kind: PostgresCustomType
    sql_definition: str

    @staticmethod
    def process_value_state(model: dict) -> Optional[T] | NullTypeState | None:
        if model is not None:
            state = model.get("state")
            if state in NullTypeState.values():
                return NullTypeState(state)
            return model.get("value")
        return None

    def get_col_spec(self, **kwargs):
        return self.kind.value

    def bind_expression(self, bindvalue):
        return bindvalue

    def result_processor(self, dialect, coltype):
        return lambda model: self.process_value_state(model)


class NullTypeEnum(BaseNullableType[NullTypeState]):
    kind = PostgresCustomType.NULL_TYPE_ENUM
    sql_definition = (
        "ENUM"
        + "("
        + ", ".join(f"'{value}'" for value in NullTypeState.values())
        + ")"
    )


class IntOrNullType(BaseNullableType[Optional[int]]):
    kind = PostgresCustomType.INT_OR_NULL
    sql_definition = "(value int, state null_type_enum)"


class TextOrNullType(BaseNullableType[Optional[str]]):
    kind = PostgresCustomType.TEXT_OR_NULL
    sql_definition = "(value text, state null_type_enum)"


class FloatOrNullType(BaseNullableType[Optional[float]]):
    kind = PostgresCustomType.FLOAT_OR_NULL
    sql_definition = "(value double precision, state null_type_enum)"


class FormOrNullType(BaseNullableType[Optional[dict]]):
    kind = PostgresCustomType.FORM_OR_NULL
    sql_definition = "(value int, state null_type_enum)"


class BoolOrNullType(BaseNullableType[Optional[bool]]):
    kind = PostgresCustomType.BOOL_OR_NULL
    sql_definition = "(value bool, state null_type_enum)"


class FileOrNullType(BaseNullableType[Optional[str]]):
    kind = PostgresCustomType.FILE_OR_NULL
    sql_definition = "(value int, state null_type_enum)"


COMPOSITE_TYPES = {
    PostgresCustomType.NULL_TYPE_ENUM: NullTypeEnum,
    PostgresCustomType.INT_OR_NULL: IntOrNullType,
    PostgresCustomType.TEXT_OR_NULL: TextOrNullType,
    PostgresCustomType.FLOAT_OR_NULL: FloatOrNullType,
    PostgresCustomType.FORM_OR_NULL: FormOrNullType,
    PostgresCustomType.BOOL_OR_NULL: BoolOrNullType,
    PostgresCustomType.FILE_OR_NULL: FileOrNullType,
}


class CompositeTypeInjector:
    def __init__(
        self,
        conn: AsyncConnection | None = None,
    ):
        self.conn = conn
        self.composite_columns = []
        self.target_tables = []

    @classmethod
    @asynccontextmanager
    async def from_session(cls, session: AsyncSession) -> Self:
        async with session.bind.connect() as conn:
            yield cls(conn)

    @property
    def select_composite_text(self) -> SimpleNamespace:
        return SimpleNamespace(
            tables=(
                "SELECT DISTINCT table_name, table_schema "
                "FROM information_schema.columns "
                "WHERE udt_name = ANY(:types) "
                "ORDER BY table_name;"
            ),
            columns=(
                "SELECT column_name, udt_name, table_schema, table_name "
                "FROM information_schema.columns "
                "WHERE udt_name = ANY(:types);"
            ),
        )

    async def create_composite_types_in_postgres(self) -> None:
        """
        Safely recreates PostgreSQL composite types (no drop statements)
        """
        for type_id, type_value in COMPOSITE_TYPES.items():
            pg_script = (
                f"DO $$ BEGIN "
                f"PERFORM 'public.{type_id}'::regtype; "
                f"EXCEPTION WHEN undefined_object THEN "
                f"CREATE TYPE public.{type_id} AS {type_value.sql_definition}; "
                f"END $$;"
            )
            await self.conn.execute(text(pg_script))
        await self.conn.commit()

    async def _get_injector_attrs(
        self,
        attr_name: str,
        query: str,
    ) -> Sequence[Any]:
        if not getattr(self, attr_name):
            result = await self.conn.execute(
                text(query),
                {"types": [enum.value for enum in COMPOSITE_TYPES.keys()]},
            )
            setattr(self, attr_name, result.all())
        return getattr(self, attr_name)

    async def get_composite_columns(self) -> Sequence[Any]:
        return await self._get_injector_attrs(
            "composite_columns",
            self.select_composite_text.columns,
        )

    async def get_target_tables(self) -> Sequence[Any]:
        return await self._get_injector_attrs(
            "target_tables", self.select_composite_text.tables
        )

    async def inject_composite_types(
        self,
    ) -> FacadeDict[str, Table]:
        """
        Injects composite types definitions for tables containing composite type columns.

        Returns
        -------
            Dictionary from actual app metadata
        FacadeDict[str, Table]

        """

        with warnings.catch_warnings(action="ignore"):
            await self.conn.run_sync(Base.metadata.reflect)

        composite_columns = await self.get_composite_columns()
        tables = Base.metadata.tables

        fixed_columns = []
        for row in composite_columns:
            column_name, udt_name, schema_name, table_name = row
            table = tables[table_name]
            if column_name in [col.name for col in table.columns]:
                type_cls = COMPOSITE_TYPES[udt_name]
                if type_cls:
                    table.columns[column_name].type = type_cls()
                    fixed_columns.append(
                        {
                            "table": table_name,
                            "column": column_name,
                            "type": udt_name,
                        }
                    )

        logger.debug(
            "Composite types fixed for columns",
            total_fixed=len(fixed_columns),
            fixed_columns=fixed_columns,
        )

        return Base.metadata.tables
