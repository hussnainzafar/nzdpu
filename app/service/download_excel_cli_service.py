from __future__ import annotations

from time import perf_counter

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.core.loaders import SubmissionLoader
from app.service.core.managers import SubmissionManager
from app.service.schema_service import SchemaService

from ..db.models import AggregatedObjectView, SubmissionObj
from ..dependencies import Cache, StaticCache
from ..loggers import get_nzdpu_logger
from ..routers.utils import get_restated_list_data_source_and_last_updated
from ..schemas.companies import CompanyEmissions
from ..schemas.submission import SubmissionGet
from ..service.exports.companies_download import CompaniesExportManager

logger = get_nzdpu_logger()


class SaveExcelFileService:
    def __init__(
        self, session: AsyncSession, static_cache: StaticCache, cache: Cache
    ):
        self._session = session
        self.static_cache = static_cache
        self.cache = cache

    async def download_company_history_cli(
        self,
        nz_id: int,
        model: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        source: int | None = None,
        exclude_classification_forced: bool | None = None,
    ):
        """
        Return emissions reported by a company by year range and data model
        used.

        Parameters
        ----------
            nz_id - The company's nz_id.
            model - The used data model to filter on.
            year_from - The starting year range.
            year_to - The ending year range.
            source - <TBD>
        """

        s = perf_counter()
        async with self._session as session:
            submission_loader = SubmissionLoader(
                session, self.static_cache, self.cache
            )
            submission_manager = SubmissionManager(
                session, self.static_cache, self.cache
            )
            try:
                orgs = await self.static_cache.organizations()
                company_name = orgs[nz_id]
            except KeyError:
                return None
            form_table = await self.static_cache.get_form_table()
            stmt = (
                select(form_table.c.obj_id)
                .join(SubmissionObj, SubmissionObj.id == form_table.c.obj_id)
                .where(SubmissionObj.nz_id == nz_id, SubmissionObj.active)
            )

            if model is not None:
                stmt = stmt.where(form_table.c.data_model == model)
            if year_from is not None:
                stmt = stmt.where(form_table.c.reporting_year >= year_from)
            if year_to is not None:
                stmt = stmt.where(form_table.c.reporting_year <= year_to)

            stmt = stmt.order_by(form_table.c.reporting_year.asc())

            result = await session.execute(stmt)
            obj_ids = [row[0] for row in result]
            aggregate_stmt = select(AggregatedObjectView).where(
                AggregatedObjectView.obj_id.in_(obj_ids)
            )
            submission_objs = (await session.scalars(aggregate_stmt)).all()

            history = []
            history_null = []
            for submission_obj in submission_objs:
                submission = submission_obj.data
                if isinstance(submission, str):
                    submission = orjson.loads(submission)

                submission_values = submission.get("values", {})
                submission_with_nulls = orjson.loads(
                    orjson.dumps(submission_values)
                )
                reporting_year = submission_values.get("reporting_year")

                # load restated fields with data source and last updated
                restated_fields_data_source = (
                    await get_restated_list_data_source_and_last_updated(
                        submission_name=submission.get("name"), session=session
                    )
                )
                if restated_fields_data_source:
                    for (
                        restated,
                        value_list,
                    ) in restated_fields_data_source.items():
                        # need to skip scope_1_greenhouse_gas, got error 422
                        if not restated.endswith("scope_1_greenhouse_gas"):
                            # unpack submission restated format
                            path = await submission_loader.unpack_restatement_path_for_restated_col(
                                submission_id=submission.get("id"),
                                restatement_path=restated,
                            )
                            # update values for every attribute
                            submission_with_nulls = submission_manager.update_values_for_restated_columns(
                                path=path,
                                values=submission_with_nulls,
                                value=value_list,
                            )
                submission_data = {
                    "id": submission.get("id"),
                    "nz_id": nz_id,
                    "name": submission.get("name"),
                    "lei": submission.get("lei"),
                    "user_id": submission.get("user_id"),
                    "submitted_by": submission.get("submitted_by"),
                    "table_view_id": submission.get("table_view_id"),
                    "permissions_set_id": submission.get("permission_set_id"),
                    "revision": submission.get("revision"),
                    "data_source": submission.get("data_source"),
                    "restated_fields_data_source": dict(
                        restated_fields_data_source.items()
                    ),
                    "status": submission.get("status"),
                    "values": submission_values,
                    "units": submission.get("units"),
                }
                submission_model = SubmissionGet(**submission_data)
                history.append(
                    {
                        "reporting_year": reporting_year,
                        "submission": submission_model,
                    }
                )
                history_null.append(
                    {
                        "reporting_year": reporting_year,
                        "submission": submission_with_nulls,
                    }
                )
            logger.debug(f"Total time: {perf_counter() - s}")

            if len(history) == 0:
                return None

            company_emission_result = CompanyEmissions(
                nz_id=nz_id,
                model=model,
                source=source,
                history=sorted(history, key=lambda x: x["reporting_year"]),
            )

            schema_service = SchemaService(static_cache=self.static_cache)
            forms_group_by = (
                await schema_service.get_group_by_forms_and_attributes()
            )

            # generate and download file
            companies_export = CompaniesExportManager(
                session=session,
                result=company_emission_result,
                stmt=stmt,
                submission_loader=submission_loader,
                company=company_name,
                static_cache=self.static_cache,
                cache=self.cache,
                forms_group_by=forms_group_by,
            )
            excel_filename = (
                await companies_export.generate_companies_download(
                    exclude_classification_forced=exclude_classification_forced
                )
            )
            return excel_filename
