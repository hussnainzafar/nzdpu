import asyncio
import itertools
import json
from collections.abc import Sequence
from typing import Any, Dict, List, Literal

from fastapi import HTTPException, status
from sqlalchemy import UnaryExpression, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AggregatedObjectView,
    ColumnDef,
    Organization,
    Restatement,
    SubmissionObj,
    TableView,
)
from app.db.redis import RedisClient
from app.schemas.restatements import AttributePathsModel
from app.schemas.search import SearchQuery
from app.schemas.submission import SubmissionGet
from app.service.core.cache import CoreMemoryCache
from app.service.core.concurrency import BatchMixin
from app.service.core.loaders import SubmissionLoader
from app.service.core.mixins import CacheMixin, SessionMixin


class QueryDSLTransformer(SessionMixin, CacheMixin):
    def __init__(
        self,
        session: AsyncSession,
        cache: CoreMemoryCache,
        redis_cache: RedisClient,
        table_view: TableView,
        query: SearchQuery,
        limit: int | None = None,
        offset: int = 0,
        submission_ids: list[int] | None = None,
    ):
        super().__init__(
            session=session, core_cache=cache, redis_cache=redis_cache
        )
        self.table_view = table_view
        self.query = query
        self.limit = limit
        self.offset = offset
        self.submission_ids = submission_ids
        self._base_query = None
        self.total_count = 0
        self.total_companies = 0

    @property
    def meta(self):
        return self.query.meta.model_dump()

    @property
    def form(self):
        return self.table_view.table_def

    async def _sort_nulls(
        self,
        order_by_clause: UnaryExpression[Any],
        order: Literal["ASC", "DESC"],
    ):
        """
        Sort the null values explicitly based on the order.
        Args:
            order_by_clause (UnaryExpression[Any]): Order clause to be sorted
            order (Literal[&quot;ASC&quot;, &quot;DESC&quot;]): Order of sorting
        """
        if order == "DESC":
            order_by_clause = order_by_clause.nulls_last()
        else:
            order_by_clause = order_by_clause.nulls_first()

        self._base_query = self._base_query.order_by(order_by_clause)

    async def build_base_query(self):
        form_table = await self.static_cache.get_form_table()
        org_table = Organization

        self._base_query = (
            select(
                form_table.c.obj_id,
                org_table.legal_name,
                org_table.lei,
                org_table.nz_id,
                org_table.jurisdiction,
                form_table.c.reporting_year,
                form_table.c.data_model,
                org_table.sics_sector,
                org_table.sics_sub_sector,
                org_table.sics_industry,
            )
            .select_from(form_table)
            .join(SubmissionObj, SubmissionObj.id == form_table.c.obj_id)
            .join(org_table, SubmissionObj.nz_id == org_table.nz_id)
        )

        # Apply filters from meta
        if "jurisdiction" in self.meta and self.meta["jurisdiction"]:
            self._base_query = self._base_query.where(
                org_table.jurisdiction.in_(self.meta["jurisdiction"])
            )

        if "reporting_year" in self.meta and self.meta["reporting_year"]:
            self._base_query = self._base_query.where(
                form_table.c.reporting_year.in_(self.meta["reporting_year"])
            )

        if "data_model" in self.meta and self.meta["data_model"]:
            self._base_query = self._base_query.where(
                form_table.c.data_model.in_(self.meta["data_model"])
            )

        sics_filters = ["sics_sector", "sics_sub_sector", "sics_industry"]
        for key in sics_filters:
            if key in self.meta and self.meta[key]:
                self._base_query = self._base_query.where(
                    getattr(org_table, key).in_(self.meta[key])
                )

        return self._base_query

    def add_default_filters(self):
        if self._base_query is None:
            raise ValueError("Base query not initialized.")

        self._base_query = self._base_query.where(
            SubmissionObj.table_view_id == self.table_view.id,
            SubmissionObj.active == True,
        )

        if self.submission_ids:
            self._base_query = self._base_query.where(
                SubmissionObj.id.in_(self.submission_ids)
            )

    def parse_offset_and_limit(self):
        if self._base_query is None:
            raise ValueError("Base query not initialized.")

        if self.limit:
            self._base_query = self._base_query.limit(self.limit)

        if self.offset:
            self._base_query = self._base_query.offset(self.offset)

    def render_query(self):
        return self._base_query

    async def set_total_count(self, statement):
        count_statement = select(func.count()).select_from(
            statement.subquery()
        )
        result = await self.session.execute(count_statement)
        self.total_count = result.scalar_one()

        company_count_query = select(
            func.count(func.distinct(statement.c.legal_name))
        )

        result = await self.session.execute(company_count_query)
        self.total_companies = result.scalar_one()

    async def transform(self):
        await self.build_base_query()
        self.add_default_filters()
        await self.set_total_count(self._base_query)
        await self.parse_sort()
        self.parse_offset_and_limit()

        return self._base_query

    def validate_sort_field(self, path: AttributePathsModel):
        allowed_fields = list(self.meta.keys()) + [
            "legal_name",
            "lei",
        ]

        if path.attribute not in allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"sort": f"Invalid field '{path.attribute}'"},
            )

    async def add_sort_for_nested_forms(
        self,
        column: ColumnDef,
        path: AttributePathsModel,
        order: str,
        parent_form: str | None = None,
    ) -> None:
        base_form_table = await self.static_cache.get_form_table()

        if path.sub_path:
            assert path.form, "Form must be specified for nested paths"

            current_form_table = await self.static_cache.get_form_table(
                path.form + "_form_heritable"
            )

            self._base_query = self._base_query.join(
                current_form_table,
                current_form_table.c.obj_id == base_form_table.c.obj_id,
            )

            if path.choice.field and path.choice.value:
                self._base_query = self._base_query.where(
                    getattr(current_form_table.c, path.choice.field)
                    == path.choice.value
                )

            await self.add_sort_for_nested_forms(
                column, path.sub_path, order, parent_form
            )
        else:
            if column.table_def.heritable:
                if not path.form:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "sort": f"Missing form in request for column '{path.attribute}'."
                        },
                    )

                current_form_table = await self.static_cache.get_form_table(
                    path.form + "_form_heritable"
                )

                subquery = select(
                    getattr(current_form_table.c, path.attribute)
                ).where(
                    and_(
                        current_form_table.c.obj_id
                        == base_form_table.c.obj_id,
                        getattr(current_form_table.c, path.attribute).is_not(
                            None
                        ),
                    )
                )

                if path.choice.field and path.choice.value:
                    subquery = subquery.where(
                        getattr(current_form_table.c, path.choice.field)
                        == path.choice.value
                    )
                if parent_form is not None:
                    subquery = subquery.where(
                        current_form_table.c.value_id == parent_form
                    )

                order_by_clause = (
                    subquery.scalar_subquery().desc()
                    if order == "DESC"
                    else subquery.scalar_subquery().asc()
                )

                # Handle NULLs explicitly based on the order
                await self._sort_nulls(order_by_clause, order)
            else:
                # Handle top-level attributes in base form table
                sort_column = getattr(base_form_table.c, path.attribute)
                order_by_clause = (
                    sort_column.desc()
                    if order == "DESC"
                    else sort_column.asc()
                )

                # Handle NULLs explicitly based on the order
                await self._sort_nulls(order_by_clause, order)

    async def parse_sort(self) -> None:
        if self._base_query is None:
            raise ValueError("Base query not initialized.")

        for sort in self.query.sort:
            if isinstance(sort, dict):
                sort_field, values = list(sort.items())[0]
                path = AttributePathsModel.unpack_field_path(sort_field)
                order = values.order.upper()
                columns = await self.static_cache.column_defs_by_name()
                column = columns.get(path.attribute)

                form_table = await self.static_cache.get_form_table()

                if not column:
                    self.validate_sort_field(path)
                    attr = getattr(
                        (
                            form_table.c
                            if hasattr(form_table.c, path.attribute)
                            else Organization
                        ),
                        path.attribute,
                    )
                    self._base_query = self._base_query.order_by(
                        attr.desc() if order == "DESC" else attr.asc()
                    )
                else:
                    await self.add_sort_for_nested_forms(column, path, order)


class SubmissionFinder(SessionMixin, CacheMixin, BatchMixin):
    def __init__(
        self,
        session: AsyncSession,
        cache: CoreMemoryCache,
        redis_cache: RedisClient,
        transformer: QueryDSLTransformer,
        export: bool = False,
        get_restated_columns: bool = False,
        batch_size: int = 50,
    ):
        super().__init__(
            session=session,
            core_cache=cache,
            redis_cache=redis_cache,
            batch_size=batch_size,
        )
        self.transformer = transformer
        self.export = export
        self.get_restated_columns = get_restated_columns

    async def search(self):
        search_query = await self.transformer.transform()
        try:
            result = await self.session.execute(search_query)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={exc},
            ) from exc
        return [row._asdict() for row in result.fetchall()]

    async def get_restated_list(self, submission_name: str) -> Dict[str, Any]:
        stmt = (
            select(
                Restatement.attribute_name,
                Restatement.data_source,
                Restatement.reporting_datetime,
            )
            .join(SubmissionObj, SubmissionObj.id == Restatement.obj_id)
            .where(SubmissionObj.name == submission_name)
            .order_by(SubmissionObj.id.asc())
        )

        results = (await self.session.execute(stmt)).all()
        return {attr: (ds, lu) for attr, ds, lu in results}

    @staticmethod
    def update_restated_columns(
        loader: SubmissionLoader, path, values, value
    ) -> None:
        keys_path = loader._get_dict_path(
            path=path, values=values, keys_path=[]
        )
        ref, key = loader._get_nethermost_dict_reference(values, keys_path)
        ref[key] = value

    async def set_restatements(
        self, loader: SubmissionLoader, submission: SubmissionGet
    ) -> None:
        restated_fields_data_source = await self.get_restated_list(
            submission_name=submission.name
        )
        for restated, value in restated_fields_data_source.items():
            if not restated.endswith("scope_1_greenhouse_gas"):
                path = await loader.unpack_restatement_path_for_restated_col(
                    submission_id=submission.id,
                    restatement_path=restated,
                )
                self.update_restated_columns(
                    loader=loader,
                    path=path,
                    values=submission.values,
                    value=value,
                )

    async def prepare_for_export(
        self,
        loader: SubmissionLoader,
        submission: SubmissionGet,
        paths: List[AttributePathsModel] | None = None,
    ) -> None:
        if self.get_restated_columns:
            await self.set_restatements(loader, submission)
        else:
            await self.set_null_values(loader, submission, paths)

    def strip_none(self, data: Any) -> Any:
        """
        Recursively strips None valued fields from a nested Python dict.

        Args:
            data (dict): A nested Python dictionary.

        Returns:
            dict: The Python dict, stripped of None valued fields.
        """
        if isinstance(data, dict):
            return {
                k: self.strip_none(v)
                for k, v in data.items()
                if k is not None
                and v is not None
                and k not in ["id", "obj_id", "value_id"]
            }
        if isinstance(data, list):
            return [self.strip_none(item) for item in data if item is not None]
        if isinstance(data, tuple):
            return tuple(
                self.strip_none(item) for item in data if item is not None
            )
        if isinstance(data, set):
            return {self.strip_none(item) for item in data if item is not None}
        return data

    async def set_null_values(
        self,
        loader: SubmissionLoader,
        submission: SubmissionGet,
        paths: list[AttributePathsModel] | None = None,
    ) -> None:
        if self.transformer.query.fields:
            submission.values = loader._strip_fields(
                submission.values, paths, raise_exception=False
            )
        else:
            submission.values = self.strip_none(submission.values)

    async def prepare_submission(
        self,
        search_result: Dict[str, Any],
        submission: SubmissionGet,
        loader: SubmissionLoader,
    ) -> SubmissionGet:
        paths = [
            AttributePathsModel.unpack_field_path(field)
            for field in self.transformer.query.fields
        ]
        await self.prepare_for_export(loader, submission, paths)
        fields_to_add = set(self.transformer.meta.keys()) | {
            "legal_name",
            "lei",
            "nz_id",
        }
        submission.values.update(
            {k: search_result[k] for k in fields_to_add if k in search_result}
        )
        submission.values["id"] = submission.id
        return submission

    async def get_submission(
        self, loader: SubmissionLoader, search_result: Dict[str, Any]
    ) -> SubmissionGet:
        obj_id = search_result["obj_id"]
        submission = await loader.load(obj_id)
        prepared_submission = await self.prepare_submission(
            search_result, submission, loader
        )

        return prepared_submission

    async def load_task(
        self, batch_list: List[Dict[str, Any]]
    ) -> List[SubmissionGet]:
        results = []
        for search_result in batch_list:
            async with AsyncSession(self.session.bind) as session:
                loader = SubmissionLoader(
                    session, self.static_cache, self.redis_cache
                )
                results.append(
                    await self.get_submission(loader, search_result)
                )
        return results

    async def merge_aggregate_data(
        self,
        loader: SubmissionLoader,
        search_obj_ids: List[int],
        search_result_mapping: Dict[int, Any],
        aggregates: Sequence[AggregatedObjectView],
    ) -> List[Dict[str, Any]]:
        aggregates_mapping = {agg.obj_id: agg for agg in aggregates}

        statement = select(SubmissionObj).where(
            SubmissionObj.id.in_(search_obj_ids)
        )
        submission_objs = (await self.session.scalars(statement)).all()
        data = []
        for idx in search_obj_ids:
            obj = next((x for x in submission_objs if x.id == idx), None)
            if obj:
                obj.values = {}
                submission_obj = SubmissionGet.model_validate(obj)
                aggregate_data = aggregates_mapping[obj.id].data
                submission_obj.values = (
                    aggregate_data.get("values")
                    if isinstance(aggregate_data, dict)
                    else json.loads(aggregate_data).get("values")
                )  # Sometimes the data is a string value otherwise is a dict. Depends on some versioning of db or libraries I guess
                prepared_submission = await self.prepare_submission(
                    search_result_mapping[obj.id], submission_obj, loader
                )
                data.append(prepared_submission.values)
        return data

    async def load_submissions_in_batches(
        self, search_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        tasks = [
            asyncio.create_task(self.load_task(batch_list=batch_results))
            for batch_results in self.batch(search_results)
        ]
        tasks_results = await asyncio.gather(*tasks)
        flat_tasks_results = list(itertools.chain(*tasks_results))
        return [task_result.values for task_result in flat_tasks_results]

    async def load_all(self) -> List[Dict[str, Any]]:
        search_results = await self.search()
        submissions = []
        loader = SubmissionLoader(
            self.session, self.static_cache, self.redis_cache
        )
        search_result_mapping = {
            result["obj_id"]: result for result in search_results
        }
        search_obj_ids = list(search_result_mapping.keys())

        statement = select(AggregatedObjectView).where(
            AggregatedObjectView.obj_id.in_(search_obj_ids)
        )
        aggregates = (await self.session.scalars(statement)).all()
        submissions = await self.merge_aggregate_data(
            loader, search_obj_ids, search_result_mapping, aggregates
        )
        diff = {obj_id for obj_id in search_obj_ids} - {
            result.obj_id for result in aggregates
        }
        if len(diff) > 0:
            search_results = [
                result for result in search_results if result["obj_id"] in diff
            ]
            submissions = await self.load_submissions_in_batches(
                search_results
            )
        return submissions
