import asyncio
from typing import Any, Generator, Iterable, Tuple

import orjson
import structlog
from async_property import async_cached_property
from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AggregatedObjectView,
    SubmissionObj,
    TableDef,
    TableView,
)
from app.db.redis import RedisClient
from app.schemas.column_def import AttributeType
from app.schemas.submission import SubmissionGet
from app.service.core.cache import CoreMemoryCache
from app.service.core.forms import FormValuesGetter
from app.service.core.mixins import CacheMixin, GetterMixin, SessionMixin

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


ID_FIELDS = {"id", "obj_id", "value_id"}


class FormBatchLoader(CacheMixin, SessionMixin):
    """
    Loads form values concurrently in a batch.

    Attributes:
        submission_id (int): `obj_id` attribute to compare table rows with
        batch_size (int): number of queries in a batch
        tasks (dict[str, asyncio.Task]): dictionary containing fetching async tasks
        form_row_data (dict[str, list[dict[str, Any]): stores the result of loading

    Methods:
        fetch_form_row_data(): Fetch form row data.
    """

    def __init__(
        self,
        session: AsyncSession,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
        submission_id: int,
        batch_size: int = 80,
    ):
        """
        Args:
            session (AsyncSession): `sqlalchemy.AsyncSession` instance
            core_cache (CoreMemoryCache): memory storage of table and columns definitions
            redis_cache (RedisClient): async redis client
            submission_id (int): `obj_id` attribute to compare table rows with
            batch_size (int): number of queries in a batch
        """

        super().__init__(core_cache, redis_cache, session)
        self.submission_id = submission_id
        self.batch_size = batch_size
        self.tasks = {}
        self.form_row_data = {}

    @async_cached_property
    async def primary_form_table_def(self) -> TableDef:
        """
        Database lookup of table_def_id of primary form,
        after which the value is retrieved from static cache

        Returns:
            TableDef: primary table definition
        """

        query = (
            select(TableView.table_def_id)
            .join(SubmissionObj, TableView.id == SubmissionObj.table_view_id)
            .where(SubmissionObj.id == self.submission_id)
        )
        table_def_id: int = (
            (await self.session.execute(query)).unique().scalar_one()
        )
        table_defs = await self.static_cache.table_defs()

        return table_defs.get(table_def_id, {})

    @async_cached_property
    async def subform_table_defs(self) -> list[TableDef]:
        """
        Recursively walk through subforms in table definition
        and return them from static cache.

        Returns:
            list[TableDef]: subform table defs
        """

        primary_td = await self.primary_form_table_def
        table_defs = await self.static_cache.table_defs()
        sub_table_defs = []

        def walk_subforms(td: TableDef):
            nonlocal table_defs
            for col in td.columns:
                if col.attribute_type in (
                    AttributeType.FORM,
                    AttributeType.FORM_OR_NULL,
                    AttributeType.MULTIPLE,
                ):
                    subform_td = table_defs[col.attribute_type_id]
                    sub_table_defs.append(subform_td)
                    walk_subforms(subform_td)

        walk_subforms(primary_td)

        return [
            table_defs.get(id, {}) for id in [td.id for td in sub_table_defs]
        ]

    @async_cached_property
    async def table_names(self) -> list[str]:
        primary_table_def = await self.primary_form_table_def
        subform_table_defs = await self.subform_table_defs
        return [
            (
                table_def.name + "_heritable"
                if table_def.heritable
                else table_def.name
            )
            for table_def in [primary_table_def] + subform_table_defs
        ]

    async def fetch_batch(
        self,
        session: AsyncSession,
        tables: list[str],
        statements: list[Select[Any]],
    ) -> None:
        """
        Coroutine for fetching batch of queries.

        Runs in a multiple tasks and stores
        the result in `self.form_row_data` attribute.
        Note that tables and statements are sorted respecting each other.

        Args:
            tables (list[str]): tables name to fetch
            statements (list[str]): queries to fetch
        """
        async with session as session:
            for i, query in enumerate(statements):
                result = (await session.execute(query)).fetchall()
                self.form_row_data[tables[i]] = [
                    row._asdict() for row in result
                ]

    @staticmethod
    def batch_split(
        tables_queries: Iterable[Tuple[str, Select[Any]]], batch_size: int
    ) -> Generator[Tuple[list[str], list[Select[Any]]], None, None]:
        """
        Queries batch generator.

        Divides number queries on batch size and yields the batch.

        Args:
            table_queries (zip): `zip` object with table and query pairs
            batch_size (int): number of queries in a batch

        Returns:
            Generator[tuple[list[str], list[Select[Any]]]]: yields batch
        """

        # Convert the zip object to a list of tuples
        tables_queries = list(tables_queries)

        # Unpack the tables and queries from the list of tuples
        tables, queries = zip(*tables_queries)

        # Calculate the number of full batches
        num_full_batches = len(tables) // batch_size

        for i in range(num_full_batches):
            start = i * batch_size
            end = start + batch_size
            yield (tables[start:end], queries[start:end])

        # Yield the remaining items if there are any
        if len(tables) % batch_size != 0:
            start = num_full_batches * batch_size
            yield (tables[start:], queries[start:])

    async def construct_query(self, table_name: str):
        """
        Query constructor helper.

        Sets ordering in a query depending on whether form is heritable.

        Args:
            table_name: name of the table

        Returns:
            A SQLAlchemy query object
        """

        # Define metadata object for dynamic table construction

        table = await self.static_cache.get_form_table(table_name)

        # Start building the query
        query = select(table).where(table.c.obj_id == self.submission_id)

        # Set ordering based on the table name
        if table_name.endswith("_heritable"):
            query = query.order_by(table.c.value_id.desc(), table.c.id)
        else:
            query = query.order_by(table.c.id)

        return query

    async def fetch_table_data(
        self,
        table_names: list[str],
    ) -> None:
        """
        Fetch select statements for every table in a list.

        Creates set of `asyncio.task` items and schedules them
        to run concurrently.

        Args:
            table_names: (list[str]) names of the table to query from
        """
        statements = {
            table: await self.construct_query(table) for table in table_names
        }

        table_statement_pairs = zip(table_names, statements.values())
        tasks = []
        for tables, statements in self.batch_split(
            table_statement_pairs, self.batch_size
        ):
            session = AsyncSession(self.session.bind)
            tasks.append(self.fetch_batch(session, tables, statements))

        await asyncio.gather(*tasks)

    async def fetch_form_row_data(self) -> dict[str, list[dict]]:
        """
        Fetch form row data.

        First gets table definitions for primary form and subforms,
        then constructs list of table names to run multiple queries in a batch.
        """
        table_names = await self.table_names
        await self.fetch_table_data(table_names)
        return self.form_row_data


class SubmissionLoader(GetterMixin):
    def __init__(
        self,
        session: AsyncSession,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
    ):
        super().__init__(session, core_cache, redis_cache)

    async def get_submission_from_cache(
        self, submission_id
    ) -> SubmissionGet | None:
        redis_key = self.redis_cache.wis_keys.submission + str(submission_id)
        submission = await self.redis_cache.get(redis_key)
        if submission is not None:
            return SubmissionGet(**orjson.loads(submission))

    async def save_submission_in_cache(
        self, key: str, submission: SubmissionGet
    ):
        submission_dict = submission.model_dump(mode="json")
        await self.redis_cache.set(
            key,
            orjson.dumps(submission_dict),  # pylint: disable=maybe-no-member
        )

    async def load_from_aggregate(
        self, submission_id: int
    ) -> SubmissionGet | None:
        statement = select(AggregatedObjectView).where(
            AggregatedObjectView.obj_id == submission_id
        )
        result = (await self.session.scalars(statement)).first()

        if result:
            data = result.data
            if isinstance(result.data, str):
                data = orjson.loads(result.data)
            return SubmissionGet(**data) if data else None

    async def load(
        self,
        submission_id: int,
        use_aggregate: bool = False,
        db_only: bool = False,
    ) -> SubmissionGet:
        if not db_only:
            cached_submission = await self.get_submission_from_cache(
                submission_id
            )
            if cached_submission:
                return cached_submission

            if use_aggregate:
                aggregate = await self.load_from_aggregate(submission_id)

                if aggregate:
                    return aggregate

        submission_obj: SubmissionObj = await self.session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == submission_id)
        )
        if not submission_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission not found: {submission_id}",
            )
        submission_obj.values = {}
        submission = SubmissionGet.model_validate(submission_obj)
        form_loader = FormBatchLoader(
            self.session, self.static_cache, self.redis_cache, submission_id
        )
        form_data = await form_loader.fetch_form_row_data()
        primary_table_def = form_loader.primary_form_table_def
        form_manager = FormValuesGetter(
            self.static_cache,
            self.redis_cache,
            form_rows=form_data,
            primary_form=primary_table_def,
        )
        submission_values, submission_units = await form_manager.get_values()
        submission.values = submission_values[0] if submission_values else {}
        submission.units = submission_units[0] if submission_units else {}
        if not db_only:
            await self.save_submission_in_cache(
                self.redis_cache.wis_keys.submission + str(submission_id),
                submission,
            )
        return submission

    async def load_by_lei_and_year(
        self,
        reported_year: int,
        lei: str,
        use_aggregate: bool = False,
        db_only: bool = False,
    ) -> SubmissionGet:
        form_table = await self.static_cache.get_form_table()

        submission_id = (
            await self.session.execute(
                select(form_table.c.obj_id)
                .join(
                    SubmissionObj,
                    SubmissionObj.id == form_table.c.obj_id,
                )
                .where(
                    SubmissionObj.lei == lei,
                    SubmissionObj.active,
                    form_table.c.reporting_year == reported_year,
                )
                .order_by(SubmissionObj.revision.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if submission_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission not found: {lei}, {reported_year}",
            )

        if not db_only:
            cached_submission = await self.get_submission_from_cache(
                submission_id
            )
            if cached_submission:
                return cached_submission

            if use_aggregate:
                aggregate = await self.load_from_aggregate(submission_id)

                if aggregate:
                    return aggregate

        submission_obj: SubmissionObj = await self.session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == submission_id)
        )
        if not submission_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission not found: {submission_id}",
            )
        submission_obj.values = {}
        submission = SubmissionGet.model_validate(submission_obj)
        form_loader = FormBatchLoader(
            self.session, self.static_cache, self.redis_cache, submission_id
        )
        form_data = await form_loader.fetch_form_row_data()
        primary_table_def = form_loader.primary_form_table_def
        form_manager = FormValuesGetter(
            self.static_cache,
            self.redis_cache,
            form_rows=form_data,
            primary_form=primary_table_def,
        )
        submission_values, submission_units = await form_manager.get_values()
        submission.values = submission_values[0] if submission_values else {}
        submission.units = submission_units[0] if submission_units else {}
        if not db_only:
            await self.save_submission_in_cache(
                self.redis_cache.wis_keys.submission + str(submission_id),
                submission,
            )
        return submission
