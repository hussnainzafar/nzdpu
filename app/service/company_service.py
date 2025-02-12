import io
from typing import Literal

from fastapi import HTTPException
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import storage
from sqlalchemy import and_, func, select, text

from app import settings
from app.db.database import DBManager
from app.db.models import Config, DataModel, Organization, SubmissionObj
from app.db.types import NullTypeState
from app.dependencies import Cache, StaticCache
from app.routers.utils import (
    get_restated_list_data_source_and_last_updated,
    process_target_progress_categories,
)
from app.schemas.companies import (
    DataModelListResponse,
    DataModelsResponse,
    JurisdictionsResponse,
    ReportingYearsResponse,
    TargetCategory,
)
from app.service.core.loaders import SubmissionLoader
from app.service.dto import CompanyDownloadOutput
from app.service.restatement_service import RestatementService

from ..loggers import get_nzdpu_logger
from ..utils import excel_filename_sics, sanitize_filename


class CompanyService:
    def __init__(self, db_manager: DBManager, static_cache: StaticCache):
        self.db_manager = db_manager
        self._session = db_manager.get_session()
        self.static_cache = static_cache
        self.logger = get_nzdpu_logger()

    async def download_companies(
        self, ref_attr: Literal["nz_id", "lei"], ref_val: int | str | None
    ) -> CompanyDownloadOutput:
        if not ref_val:
            raise HTTPException(
                status_code=400,
                detail="Either nz_id or lei must be provided",
            )
        orgs_t = Organization.__table__

        if ref_attr in orgs_t.c:
            stmt = select(Organization).where(
                orgs_t.columns[ref_attr] == ref_val
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reference attribute for organization table:{ref_attr}",
            )

        company = (await self._session.execute(stmt)).scalar_one_or_none()
        if company is None:
            raise HTTPException(
                status_code=404,
                detail="No company found with the provided LEI",
            )

        db_config_value = select(Config.value).where(
            Config.name == "data_download.exclude_classification"
        )
        # execute the query and get the result for sics available
        exclude_classification_value = await self._session.execute(
            db_config_value
        )
        exclude_classification = exclude_classification_value.scalars().first()
        if exclude_classification:
            exclude_classification = int(exclude_classification)

        extension = ".xlsx"
        filename = (
            sanitize_filename(
                prefix="nzdpu",
                company=company.legal_name,
                nz_id=str(company.nz_id),
            )
            + excel_filename_sics(
                exclude_classification_forced=exclude_classification == 1
            )
            + extension
        )
        self.logger.debug(f"Retrieving file {filename} from bucket")

        storage_client = storage.Client(project=settings.gcp.project)
        bucket = storage_client.get_bucket(settings.gcp.default_bucket)

        blob = bucket.blob(filename)

        # Create an in-memory bytes buffer
        file_stream = io.BytesIO()
        try:
            blob.download_to_file(client=storage_client, file_obj=file_stream)
            file_stream.seek(0)
        except GoogleAPICallError as exc:
            self.logger.error(
                "Google GCP Bucket API error occured",
                message=exc.message,
                reason=exc.reason,
                code=exc.code,
            )
            raise exc
        return CompanyDownloadOutput(file_stream, filename)

    async def get_jurisdictions(
        self,
    ) -> JurisdictionsResponse:
        """
        Return the jurisdictions for a company


        Returns
        -------
            jurisdictions - List of jurisdictions
        """
        query = (
            select(Organization.jurisdiction)
            .join(SubmissionObj, SubmissionObj.nz_id == Organization.nz_id)
            .order_by(text("jurisdiction ASC"))
            .distinct()
        )

        result = await self._session.execute(query)

        # Convert the result to a list of dictionaries (or lists of values)
        jurisdictions = [row[0] for row in result]

        return JurisdictionsResponse(jurisdictions=jurisdictions)

    async def get_reporting_years(
        self,
        nz_id: int | None = None,
    ) -> ReportingYearsResponse:
        """
        Return the reported years for a company

        Parameters
        ----------
            nz_id - Unique identifier of the company

        Returns
        -------
            reporting_years - List of reported years
        """
        form_table = await self.static_cache.get_form_table()
        query = (
            select(form_table.c.reporting_year)
            .join(SubmissionObj, SubmissionObj.id == form_table.c.obj_id)
            .order_by(text("reporting_year DESC"))
            .distinct()
        )

        if nz_id is not None:
            query = query.where(SubmissionObj.nz_id == nz_id)

        result = await self._session.execute(query)

        # Convert the result to a list of dictionaries (or lists of values)
        reporting_years = [row[0] for row in result]

        return ReportingYearsResponse(reporting_years=reporting_years)

    async def get_data_models(
        self,
    ) -> DataModelsResponse:
        """
        Return the available data models for a company

        Returns
        -------
            data_models - List of DataModelsResponse
        """
        form_table = await self.static_cache.get_form_table()
        query = select(DataModel)
        result = await self._session.execute(query)
        data = result.all()
        models = []
        for row in data:
            models.append(
                DataModelListResponse(
                    id=row[0].id,
                    name=row[0].name,
                    table_view_id=row[0].table_view_id,
                )
            )
        return DataModelsResponse(data_models=models)

    async def get_most_recent_reporting_year(self) -> int:
        """
        Return the most recent reporting year

        Returns
        -------
            most_recent_reporting_year - Most recent reporting year
        """
        form_table = await self.static_cache.get_form_table()
        query = select(func.max(form_table.c.reporting_year))

        result = await self._session.execute(query)

        # Convert the result to a list of dictionaries (or lists of values)
        most_recent_reporting_year = result.scalar_one_or_none()

        # If there is no data in the database, return 0
        if most_recent_reporting_year is None:
            return 0

        return most_recent_reporting_year

    async def get_sources(
        self, nz_id: int | None = None, order_desc=False
    ) -> list[str]:
        """
        Return the available sources

        Returns
        -------
            sources - List of sources
        """
        form_table = await self.static_cache.get_form_table()
        query = (
            select(form_table.c.disclosure_source)
            .distinct()
            .order_by(
                form_table.c.disclosure_source.desc()
                if order_desc
                else form_table.c.disclosure_source.asc()
            )
        )

        if nz_id is not None:
            query = query.join(
                SubmissionObj, SubmissionObj.id == form_table.c.obj_id
            ).where(SubmissionObj.nz_id == nz_id)

        result = await self._session.execute(query)

        # Convert the result to a list of dictionaries (or lists of values)
        sources = [row[0] for row in result]

        return sources

    def _get_sub_query_max_revision_grouped_by_nz_id_source(self, nz_id: int):
        return (
            select(
                SubmissionObj.nz_id,
                SubmissionObj.data_source,
                func.max(SubmissionObj.revision).label("max_revision"),
            )
            .where(SubmissionObj.nz_id == nz_id)
            .group_by(SubmissionObj.nz_id, SubmissionObj.data_source)
            .subquery()
        )

    async def get_intensity_targets(
        self, active: bool, nz_id: int, source_param: str | None
    ):
        nzdpu_form = await self.static_cache.get_form_table()

        intensity_data_columns = [
            # "tgt_int_intensity_type",
            "tgt_int_year_set",
            "tgt_int_base_year",
            "tgt_int_cvg_scope",
            "tgt_int_status",
            "tgt_int_id",
            "tgt_int_name",
        ]

        sub_query_max_revision = (
            self._get_sub_query_max_revision_grouped_by_nz_id_source(nz_id)
        )

        intensity_form_table = await self.static_cache.get_form_table(
            "tgt_int_dict_form_heritable"
        )

        query_int = (
            select(
                nzdpu_form.c.reporting_datetime,
                SubmissionObj.data_source,
                *[
                    getattr(intensity_form_table.c, col)
                    for col in intensity_data_columns
                ],
            )
            .join(SubmissionObj, SubmissionObj.id == nzdpu_form.c.obj_id)
            .join(
                intensity_form_table,
                SubmissionObj.id == intensity_form_table.c.obj_id,
            )
            .join(
                sub_query_max_revision,
                (
                    SubmissionObj.revision
                    == sub_query_max_revision.c.max_revision
                )
                & (
                    SubmissionObj.data_source
                    == sub_query_max_revision.c.data_source
                ),
            )
            .where(SubmissionObj.nz_id == nz_id)
        )

        query_int = query_int.where(
            text("LOWER((tgt_int_status).value) = 'active'")
            if active
            else text("LOWER((tgt_int_status).value) != 'active'")
        )

        if source_param:
            query_int = query_int.where(
                SubmissionObj.data_source == source_param
            )

        int_result = await self._session.execute(query_int)

        return list(int_result)

    async def get_absolute_targets(
        self, active: bool, nz_id: int, source_param: str | None
    ):
        nzdpu_form = await self.static_cache.get_form_table()
        absolute_form_table = await self.static_cache.get_form_table(
            "tgt_abs_dict_form_heritable"
        )

        absolute_data_columns = [
            "tgt_abs_year_set",
            "tgt_abs_base_year",
            "tgt_abs_cvg_scope",
            "tgt_abs_status",
            "tgt_abs_id",
            "tgt_abs_name",
        ]

        sub_query_max_revision = (
            self._get_sub_query_max_revision_grouped_by_nz_id_source(nz_id)
        )

        query_abs = (
            select(
                nzdpu_form.c.reporting_datetime,
                SubmissionObj.data_source,
                *[
                    getattr(absolute_form_table.c, col)
                    for col in absolute_data_columns
                ],
            )
            .join(SubmissionObj, SubmissionObj.id == nzdpu_form.c.obj_id)
            .join(
                absolute_form_table,
                SubmissionObj.id == absolute_form_table.c.obj_id,
            )
            .join(
                sub_query_max_revision,
                (
                    SubmissionObj.revision
                    == sub_query_max_revision.c.max_revision
                )
                & (
                    SubmissionObj.data_source
                    == sub_query_max_revision.c.data_source
                ),
            )
            .where(SubmissionObj.nz_id == nz_id)
        )

        query_abs = query_abs.where(
            text("LOWER((tgt_abs_status).value) = 'active'")
            if active
            else text("LOWER((tgt_abs_status).value) != 'active'")
        )

        if source_param:
            query_abs = query_abs.where(
                SubmissionObj.data_source == source_param
            )

        abs_result = await self._session.execute(query_abs)

        return list(abs_result)

    async def get_single_target_progress(
        self,
        nz_id: int,
        tgt_id: str,
        tgt_category: TargetCategory,
        cache: Cache,
        data_source: str | None = None,
    ):
        tgt_category_short = (
            "abs" if tgt_category == TargetCategory.ABSOLUTE else "int"
        )
        tgt_form = f"tgt_{tgt_category_short}_progress_dict_form_heritable"
        tgt_form_id = f"tgt_{tgt_category_short}_id"

        position = await self.get_target_position(
            nz_id=nz_id,
            tgt_id=tgt_id,
            tgt_category=tgt_category_short,
            data_source=data_source,
        )

        # construct query
        nzdpu_form_table = await self.static_cache.get_form_table()
        stmt = (
            select(
                nzdpu_form_table.c.obj_id,
                nzdpu_form_table.c.tgt_abs_progress_dict,
                nzdpu_form_table.c.tgt_int_progress_dict,
            )
            .join(
                SubmissionObj,
                SubmissionObj.id == nzdpu_form_table.c.obj_id,
            )
            .where(SubmissionObj.nz_id == nz_id)
        )
        if data_source:
            stmt = stmt.where(SubmissionObj.data_source == data_source)
        # execute the query
        result = await self._session.execute(stmt)
        submission_loader = SubmissionLoader(
            self._session, self.static_cache, cache
        )
        # check which submissions have target_progress
        sub_obj = None
        for sub_id, tgt_abs_value, tgt_int_value in result.fetchall():
            if (
                tgt_abs_value is not None
                and tgt_abs_value not in NullTypeState.values()
            ) or (
                tgt_int_value is not None
                and tgt_int_value not in NullTypeState.values()
            ):
                target_progress_table = await self.static_cache.get_form_table(
                    tgt_form
                )
                target_progress_column = (
                    target_progress_table.c.tgt_abs_id_progress
                    if tgt_category == TargetCategory.ABSOLUTE
                    else target_progress_table.c.tgt_int_id_progress
                )
                query = select(target_progress_table.c.obj_id).where(
                    and_(
                        target_progress_table.c.obj_id == sub_id,
                        target_progress_column == tgt_id,
                    )
                )

                submission_result = await self._session.execute(query)
                submission_id = submission_result.scalar()
                if submission_id:
                    sub_obj = await submission_loader.load(
                        submission_id=submission_id,
                        use_aggregate=True,
                    )
        if sub_obj:
            restated = await get_restated_list_data_source_and_last_updated(
                submission_name=sub_obj.name,
                session=self._session,
                only_last_attribute=True,
            )
            for targets in sub_obj.values.get(
                f"tgt_{tgt_category_short}_progress_dict"
            ):
                targets_root = next(
                    (
                        tgt
                        for tgt in sub_obj.values.get(
                            f"tgt_{tgt_category_short}_progress_dict"
                        )
                        if tgt.get(f"{tgt_form_id}_progress") == tgt_id
                    ),
                    None,
                )
                targets_root_second = next(
                    (
                        tgt
                        for tgt in sub_obj.values.get(
                            f"tgt_{tgt_category_short}_dict"
                        )
                        if tgt.get(tgt_form_id) == tgt_id
                    ),
                    None,
                )
                # combine progress and root targets to get dynamic units
                targets_root.update(targets_root_second)
                if targets.get(f"{tgt_form_id}_progress") == tgt_id:
                    restatement_service = RestatementService(
                        db_manager=self.db_manager
                    )
                    restatements = await restatement_service.get_restatements_by_submission_ids(
                        [submission_id]
                    )

                    attribute_name_last_update_dict = restatement_service.get_attribute_name_last_update_mapper_for_tgt(
                        restatements, position=position
                    )
                    attribute_name_last_source_dict = restatement_service.get_attribute_name_last_source_mapper_for_tgt(
                        restatements, position=position
                    )
                    tgt_progress_dict = (
                        await process_target_progress_categories(
                            targets_root,
                            targets,
                            sub_obj.data_source,
                            f"{tgt_form_id}_progress",
                            self._session,
                            self.static_cache,
                            sub_obj.values.get("reporting_datetime"),
                            attribute_name_last_update_dict,
                            attribute_name_last_source_dict,
                        )
                    )
                    tgt_progress_dict["reporting_year"] = sub_obj.values.get(
                        "reporting_year"
                    )
                    return tgt_progress_dict
        else:
            raise HTTPException(
                status_code=404, detail="Targets progress not found"
            )

    async def get_target_position(
        self, nz_id: int, tgt_id: str, tgt_category: str, data_source: str
    ):
        targets = []
        if tgt_category == "abs":
            targets = await self.get_absolute_targets(True, nz_id, data_source)
        elif tgt_category == "int":
            targets = await self.get_intensity_targets(
                True, nz_id, data_source
            )

        # we need to know which is the position of the target when it was inserted
        # so that we know for each target we are looking for restatements
        return next(
            (i for i, item in enumerate(targets) if item[6] == tgt_id),
            -1,
        )
