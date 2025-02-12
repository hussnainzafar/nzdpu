"""Search DSL class."""

import asyncio
import itertools
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import Table, and_, not_, select, text
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Base
from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader

from .db.models import (
    Choice,
    ColumnDef,
    Organization,
    SubmissionObj,
    TableView,
)
from .db.redis import RedisClient
from .db.types import NullTypeState
from .loggers import get_nzdpu_logger
from .routers.utils import (
    ErrorMessage,
    get_restated_list_data_source_and_last_updated,
    load_organization_by_lei,
)
from .schemas.column_def import AttributeType
from .schemas.restatements import AttributePathsModel
from .schemas.search import (
    SearchDSLStatement,
    SearchQuery,
)
from .service.core.types import ColumnDefsDataByName
from .service.core.utils import strip_none

logger = get_nzdpu_logger()


@dataclass
class SearchDSL:
    """
    SearchDSL class.

    Args:
        session (AsyncSession) - the SQLAlchemy session
        query (SearchQuery) - the search query
        offset (int, optional) - The query offset. Defaults to 0.
        limit (int | None, optional) - The query limit. Defaults to
            None.
    """

    static_cache: CoreMemoryCache
    cache: RedisClient
    session: AsyncSession
    query: SearchQuery
    view_id: int
    offset: int = 0
    limit: Optional[int] = None
    submission_ids: Optional[List[int]] = None
    _stmt: SearchDSLStatement = field(default_factory=SearchDSLStatement)
    form: str = ""
    total_count: int = 0

    async def _handle_select(self) -> None:
        """
        Constructs SELECT statements from the "select" section of the query.
        """

        # Get form from table_view_id
        try:
            table_view = await self.session.scalar(
                select(TableView).where(TableView.id == self.view_id)
            )
        except NoResultFound:
            table_view = self.static_cache.table_views.get(self.view_id)

        if not table_view:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE},
            )

        table_def = table_view.table_def
        self.form = str(table_def.name)
        # Assume these are SQLAlchemy Table objects or models

        form_table = await self.static_cache.get_form_table(self.form)

        # Build the select statement
        stmt = select(
            form_table.c.obj_id,
            Organization.legal_name,
            Organization.lei.label("lei"),
            Organization.jurisdiction,
        ).select_from(form_table)

        # Add data_model field to select and where
        if self.query.meta.data_model:
            stmt = (
                stmt.add_columns(
                    form_table.c.data_model.label("data_model_id"),
                    Choice.value.label("data_model"),
                )
                .join(
                    Choice,
                    Choice.choice_id == form_table.c.data_model,
                )
                .where(form_table.c.data_model == self.query.meta.data_model)
            )

        # Join submission_obj
        stmt = stmt.join(
            SubmissionObj, SubmissionObj.id == form_table.c.obj_id
        )

        # Save the statement
        self._final_stmt = stmt

    def _handle_jurisdiction(self, jurisdiction: list[str]) -> str:
        # Transform list of strings into a string appropriate to use in SQL IN operator
        # [jur1, jur2, jur3] -> "'jur1','jur2','jur3'"

        sql_escaped_jurisdictions = [
            jur.replace("'", "''") for jur in jurisdiction
        ]
        single_quote_surrounded_jurisdictions = [
            f"'{jur}'" for jur in sql_escaped_jurisdictions
        ]

        return ",".join(single_quote_surrounded_jurisdictions)

    def _handle_meta(self):
        """
        Handles meta section of the search query.
        """
        # Unpack self.query.meta
        jurisdiction = self.query.meta.jurisdiction
        reporting_year = self.query.meta.reporting_year
        sics_sector = self.query.meta.sics_sector
        sics_subsector = self.query.meta.sics_sub_sector
        sics_industry = self.query.meta.sics_industry

        # Assume these are SQLAlchemy Table objects or models
        form_table = Table(
            self.form, Base.metadata, autoload_with=self.session.bind
        )

        # Join organization on user
        self._final_stmt = self._final_stmt.join(
            Organization,
            SubmissionObj.nz_id == Organization.nz_id,
        )

        if jurisdiction:
            jurisdictions = self._handle_jurisdiction(jurisdiction)
            self._final_stmt = self._final_stmt.where(
                Organization.jurisdiction.in_(jurisdictions)
            )

        if reporting_year:
            self._final_stmt = self._final_stmt.add_columns(
                form_table.c.reporting_year.label("reporting_year")
            )
            self._final_stmt = self._final_stmt.where(
                form_table.c.reporting_year.in_(reporting_year)
            )

        if sics_sector:
            sics_sectors = ",".join([f"'{s}'" for s in sics_sector])
            self._final_stmt = self._final_stmt.where(
                Organization.sics_sector.in_(sics_sectors)
            )

        if sics_subsector:
            sics_subsectors = ",".join([f"'{s}'" for s in sics_subsector])
            self._final_stmt = self._final_stmt.where(
                Organization.sics_sub_sector.in_(sics_subsectors)
            )

        if sics_industry:
            sics_industries = ",".join([f"'{s}'" for s in sics_industry])
            self._final_stmt = self._final_stmt.where(
                Organization.sics_industry.in_(sics_industries)
            )

    async def _add_order_by_for_subform_fields(
        self,
        column: ColumnDef,
        path: AttributePathsModel,
        order: str,
        *,
        _parent_form: str | None = None,
    ) -> None:
        """
        Adds selects for order by clauses on sub-forms.

        To order by fields in nested sub-forms, joining tables would
        return multiple rows per submission. Ordering by the result of
        an additional select clause, we can filter for fields only from
        the obj_ids retrieved in the parent SQL query.

        Args:
            path (AttributePathsModel): The attribute path from the sort
                section of the SearchDSLQuery object.
            order (SortOrderEnum): The sort order.
        """
        # Recursively process sub-paths first
        if path.sub_path is not None:
            assert path.form
            form = path.form + "_form_heritable"

            form_table = await self.static_cache.get_form_table()
            self_form_table = await self.static_cache.get_form_table(self.form)

            # Construct the join and sub-select statement
            subquery = select(
                getattr(form_table, path.sub_path.attribute)
            ).join(form_table, form_table.c.obj_id == self_form_table.c.obj_id)

            if path.choice.field and path.choice.value is not None:
                subquery = subquery.where(
                    form_table.c[path.choice.field] == path.choice.value
                )

            # Recurse into deeper sub-paths
            await self._add_order_by_for_subform_fields(
                column=column,
                path=path.sub_path,
                order=order,
                _parent_form=form,
            )

        else:
            if column.table_def.heritable:
                if not path.form:
                    # Raise an error if parent form is missing in the request
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "sort": (
                                f"Missing parent form in request for column"
                                f" {column.name!r}."
                            )
                        },
                    )

                form = path.form + "_form_heritable"
                form_table = await self.static_cache.get_form_table(form)

                # Construct sub-select for ordering
                subquery = select(getattr(form_table, path.attribute)).where(
                    and_(
                        form_table.c.obj_id == self.form.c.obj_id,
                        form_table.c[path.attribute]
                        != None,  # Equivalent to "is not null"
                    )
                )

                if path.choice.field and path.choice.value is not None:
                    subquery = subquery.where(
                        form_table.c[path.choice.field] == path.choice.value
                    )

                if _parent_form is not None:
                    subquery = subquery.where(
                        form_table.c.value_id == _parent_form.c[path.form]
                    )

            else:
                # Sub-query for non-heritable columns
                subquery = select(path.attribute).where(
                    path.attribute != None  # Equivalent to "is not null"
                )

            # Additional filter for null-like values for integer-type columns
            if column.attribute_type in {
                AttributeType.INT,
                AttributeType.FORM,
                AttributeType.SINGLE,
                AttributeType.MULTIPLE,
                AttributeType.FLOAT,
            }:
                subquery = subquery.where(
                    not_(path.attribute.in_(NullTypeState.values()))
                )

            # Apply the order_by clause using the sub-query
            self._final_stmt = self._final_stmt.order_by(
                subquery.as_scalar().label(order)
            )

    async def _handle_sort(self, columns: ColumnDefsDataByName) -> None:
        """
        Handles the sort section of the search query.
        """
        for sort_element in self.query.sort:
            assert isinstance(sort_element, dict)
            sort_field, values = list(sort_element.items())[0]
            path = AttributePathsModel.unpack_field_path(sort_field)
            order = values.order.upper()
            column = columns.get(path.attribute)
            if column is None:
                # field is not a column: add "standard" order by
                self._validate_field(field=path.attribute)
                sort_statement = f"{path.attribute} {order}"
                self._final_stmt = self._final_stmt.order_by(
                    text(sort_statement)
                )
            else:
                # field is a column: order by on sub select
                await self._add_order_by_for_subform_fields(
                    column=column, path=path, order=order
                )

    def _add_default_fields(self):
        if "sics_sector" in self.query.fields:
            select_stmt = Organization.sics_sector.label("sics_sector")
            self._final_stmt = self._final_stmt.add_columns(select_stmt)

        if "sics_sub_sector" in self.query.fields:
            select_stmt = Organization.sics_sub_sector.label("sics_sub_sector")
            self._final_stmt = self._final_stmt.add_columns(select_stmt)

        if "sics_industry" in self.query.fields:
            select_stmt = Organization.sics_industry.label("sics_industry")
            self._final_stmt = self._final_stmt.add_columns(select_stmt)

    def _add_offset_and_limit(self):
        """
        Add LIMIT and OFFSET.
        """
        # sqlite and postgres have different approach to limit and offset
        if str(self.session.get_bind().engine.url).startswith("sqlite"):
            if self.limit is not None:
                self._final_stmt = self._final_stmt.limit(self.limit)
                self._final_stmt = self._final_stmt.offset(self.offset)
        else:
            self._final_stmt = self._final_stmt.limit(
                self.limit if self.limit else None
            )
            self._final_stmt = self._final_stmt.offset(self.offset)

    def _validate_field(self, field: str):
        """
        Checks provided field is a column of the WIS.

        Args:
            field (str): The field name.

        Raises:
            HTTPException: 422 if field is invalid.
        """
        additional_valid_fields_for_sorting = {"legal_name", "lei"}

        if (
            field
            not in set(self.query.meta.model_dump().keys())
            | additional_valid_fields_for_sorting
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"sort": f"Invalid field '{field}'"},
            )

    async def _execute(
        self, columns: ColumnDefsDataByName
    ) -> list[dict[str, Any]]:
        """
        Executes the query defined in self._final_stmt.

        Returns:
            list: The query results
        """

        # Add filter on table_view_id
        self._final_stmt = self._final_stmt.where(
            SubmissionObj.table_view_id == self.view_id
        )
        self._final_stmt = self._final_stmt.where(SubmissionObj.active == True)

        if self.submission_ids:
            self._final_stmt = self._final_stmt.where(
                SubmissionObj.id.in_(self.submission_ids)
            )

        # Construct select clause for download
        await self._handle_select()

        # Handle fields in meta section
        self._handle_meta()

        # Add selects from `query.fields`
        self._add_default_fields()

        # Execute count query here before setting sort, offset, and limit
        # to get count of total items
        total_count_result = await self.session.scalars(self._final_stmt)
        self.total_count = len(list(total_count_result))

        # Add sorting
        await self._handle_sort(columns=columns)

        # Add offset and limit
        self._add_offset_and_limit()

        # Execute all queries
        results = [
            # Link column names to values
            dict(zip(row._fields, row))
            for row in await self.session.execute(self._final_stmt)
        ]

        return results

    async def _get_submission(
        self,
        result: dict[str, Any],
        submission_loader: SubmissionLoader,
        submission_id: int,
        export: bool = False,
    ):
        # Load submission data
        submission = await self._load_submission_data(
            submission_loader, submission_id
        )

        # Process submission values
        await self._process_submission_values(
            submission, submission_loader, export
        )

        # Add additional fields to submission
        submission = self._add_additional_fields_to_submission(
            submission, result
        )

        return submission

    async def _load_submission_data(
        self, submission_loader: SubmissionLoader, submission_id: int
    ) -> Any:
        """Load the submission data using the loader."""
        return await submission_loader.load(submission_id=submission_id)

    async def _get_company_by_lei(self, submission: Any) -> Any:
        """Fetch company data based on the legal entity identifier."""
        submission_lei = submission.values.get("legal_entity_identifier")
        return (
            await load_organization_by_lei(submission_lei, self.session)
            if submission_lei
            else None
        )

    async def _process_submission_values(
        self,
        submission: Any,
        submission_loader: SubmissionLoader,
        export: bool,
    ) -> None:
        """Process the submission values and handle export logic."""
        if export:
            await self._handle_restated_fields(submission, submission_loader)
        else:
            await self._strip_submission_fields(submission, submission_loader)

    async def _handle_restated_fields(
        self, submission: Any, submission_loader: SubmissionLoader
    ):
        """Handle restated fields logic."""
        restated_fields_data_source = (
            await get_restated_list_data_source_and_last_updated(
                submission_name=submission.name, session=self.session
            )
        )
        for restated, value in restated_fields_data_source.items():
            if not restated.endswith("scope_1_greenhouse_gas"):
                path = await submission_loader.unpack_restatement_path_for_restated_col(
                    submission_id=submission.id, restatement_path=restated
                )
                submission.values = (
                    submission_loader.update_values_for_restated_columns(
                        path=path, values=submission.values, value=value
                    )
                )

    async def _strip_submission_fields(
        self, submission: Any, submission_loader: SubmissionLoader
    ) -> None:
        """Strip fields from submission values based on query fields."""
        if self.query.fields:
            submission.values = submission_loader._strip_fields(
                submission.values,
                [
                    AttributePathsModel.unpack_field_path(field)
                    for field in self.query.fields
                ],
                raise_exception=False,
            )
        else:
            submission.values = strip_none(submission.values)

    def _add_additional_fields_to_submission(
        self, submission: Any, result: dict[str, Any]
    ) -> Any:
        """Add additional fields to the submission object."""
        fields_to_add = set(self.query.meta.model_dump().keys()) | {
            "legal_name",
            "lei",
        }
        submission.values.update(
            {k: result[k] for k in fields_to_add if k in result}
        )
        submission.values["id"] = submission.id
        return submission

    async def get_submission(self, batch_results, export, submission_loader):
        results = []
        for result in batch_results:
            submission_id = result["obj_id"]
            submission = await self._get_submission(
                result=result,
                submission_loader=submission_loader,
                submission_id=submission_id,
                export=export,
            )
            results.append(submission)
        return results

    def batch(self, batch_size: int, results):
        num_batches = len(results) // batch_size
        for i in range(num_batches):
            start = i * batch_size
            end = start + batch_size
            yield results[start:end]

        if len(results) % batch_size != 0:
            start = num_batches * batch_size
            yield results[start:]

    async def get_results(self, export=False) -> list[dict[str, Any]]:
        """
        From the results returned by _execute, loads all submissions
        and strips only the requested fields.

        Returns:
            list: The submissions.
        """

        s = perf_counter()
        submission_loader = SubmissionLoader(
            redis_cache=self.cache,
            session=self.session,
            core_cache=self.static_cache,
        )
        columns = await self.static_cache.column_defs_by_name()
        results = await self._execute(columns)
        logger.debug(f"Search query executed in {perf_counter() - s}")
        # get submissions from results
        batch_size = 80
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self.get_submission(
                        batch_results=batch_results,
                        export=export,
                        submission_loader=submission_loader,
                    )
                )
                for batch_results in self.batch(batch_size, results)
            ]
            tasks_results = await asyncio.gather(*tasks)
            flat_tasks_results = list(itertools.chain(*tasks_results))
            submissions = [
                task_result.values for task_result in flat_tasks_results
            ]

        return submissions
