"""Companies"""

from __future__ import annotations

import csv
import json
import re
import tempfile
from datetime import datetime
from time import perf_counter
from typing import Any
from urllib.parse import unquote

import orjson
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from google.api_core.exceptions import GoogleAPICallError
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import CTE, RowMapping, Table, and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Select

from app.forms.attribute_reader.utils import object_as_dict
from app.routers.utils import (
    process_target_progress_categories,
    track_api_usage,
)
from app.service.company_service import CompanyService
from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader
from app.service.history_service import HistoryService
from app.service.organization_service import OrganizationService
from app.service.query_helpers import get_order_by
from app.service.restatement_service import RestatementService
from app.service.schema_service import SchemaService
from app.utilities.utils_string import consistent_hash

from ..db.models import (
    AggregatedObjectView,
    AuthRole,
    Config,
    Organization,
    OrganizationAlias,
    Restatement,
    SubmissionObj,
    User,
)
from ..db.types import NullTypeState
from ..dependencies import (
    Cache,
    DbManager,
    RoleAuthorizationForMultipleAuth,
    StaticCache,
    get_current_user_or_none,
)
from ..forms.form_meta import FormMeta
from ..loggers import get_nzdpu_logger
from ..routers.utils import (
    create_cache_key,
    get_restated_fields_data_source,
    normalize_text,
)
from ..schemas.companies import (
    AbsoluteDataModel,
    AbsoluteDataModelWrapper,
    CompaniesListElement,
    CompaniesListElementWithNonLeiIdentifiers,
    CompaniesSpecificCriteriaList,
    CompanyDisclosures,
    CompanyEmissions,
    CompanyRestatementsResponseModel,
    DataModelsResponse,
    DataSourcesResponse,
    DisclosureSortByEnum,
    GetTargetById,
    IntensityDataModel,
    IntensityDataModelWrapper,
    JurisdictionsResponse,
    MostRecentYear,
    ReportingYearsResponse,
    Target,
    TargetBySource,
    TargetCategory,
    TargetsProgressResponse,
    TargetsProgressSingleResponse,
    TargetsResponse,
    TargetsValidationSchema,
)
from ..schemas.enums import SICSSectorEnum
from ..schemas.restatements import (
    AttributePathsModel,
    RestatementAttributePrompt,
    RestatementGet,
    RestatementList,
    RestatementOriginal,
)
from ..schemas.submission import DisclosureDetailsResponse, SubmissionGet
from ..schemas.tracking import TrackingUrls
from ..service.exports.utils import get_attribute_prompt_from_path
from ..service.utils import format_units

router = APIRouter(
    prefix="/coverage/companies",
    tags=["companies"],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

logger = get_nzdpu_logger()


def check_where(stmt: str):
    if "WHERE" in stmt:
        stmt += " AND"
    else:
        stmt += " WHERE"

    return stmt


def escape_sql_chars(text: str) -> str:
    return text.replace("'", "''").replace("%", "\\%").replace("_", "\\_")


class CompanySearchQuery(BaseModel):
    jurisdiction: str | list[str] | None = None
    name: str | None = None
    lei: str | None = None
    nz_id: int | list[str] | None = None
    sics_sector: str | list[str] | None = None
    source: list[str] | None = None
    latest_reported_year: str | list[int] | None = None

    start: int = 0
    limit: int = 10
    order_by: str = "legal_name"
    order: str = "ASC"
    free: str | None = None

    @field_validator("nz_id", "latest_reported_year", mode="before")
    @classmethod
    def validate_int_comma_list(cls, v: Any) -> list[int] | None:
        if isinstance(v, str):
            try:
                return [int(s.strip()) for s in v.split(",") if s.strip()]
            except ValueError:
                raise ValueError("All values must be integers")
        return v

    @field_validator(
        "jurisdiction", "lei", "sics_sector", "source", mode="before"
    )
    @classmethod
    def validate_str_comma_list(cls, v: Any) -> list[str] | None:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("sics_sector", mode="after")
    @classmethod
    def validate_sics_sector(cls, v: str | list[str] | None) -> Any:
        if v is not None:
            valid_sectors = {sector.value for sector in SICSSectorEnum}
            for sector in v:
                if sector not in valid_sectors:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Invalid SICS sector - {sector}. Must be in"
                            " the list of allowed sectors."
                        ),
                    )
            return v

    @classmethod
    def from_request(cls, request: Request) -> CompanySearchQuery:
        query_string = unquote(request.scope["query_string"].decode())
        pattern = r"([^&=]+)=([^&]*(?:&(?![^&=]+=)[^&]*)*)"
        matches = re.findall(pattern, query_string)
        query_params = {}
        for key, value in matches:
            key = key.strip()
            value = value.strip()

            if key in ["start", "limit"]:
                try:
                    query_params[key] = int(value)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid value for {key}: {value}. Expected an integer."
                    ) from exc
            else:
                query_params[key] = value

        return cls(**query_params)


def add_fuzzy_match_to_stm(free: str, cte: CTE):
    (stmt, score_label) = OrganizationService.get_select_fuzzy_match_stmt(
        free,
        [
            Organization,
            OrganizationAlias.alias,
            cte.c.source,
            cte.c.latest_reported_year,
        ],
    )

    stmt = stmt.join(
        OrganizationAlias,
        OrganizationAlias.nz_id == cte.c.nz_id,
        isouter=True,
    )

    return stmt.order_by(text(f"{score_label} DESC"))


def add_sub_string_match_to_stm(free: str, cte: CTE):
    stmt = OrganizationService.get_select_sub_string_match_stmt(
        free,
        [
            Organization,
            OrganizationAlias.alias,
            cte.c.source,
            cte.c.latest_reported_year,
        ],
    )

    stmt = stmt.join(
        OrganizationAlias,
        OrganizationAlias.nz_id == cte.c.nz_id,
        isouter=True,
    )

    return stmt


def get_organization_order_by_text_stmt(order_by: str, order: str):
    if order_by != "latest_reported_year" and order_by != "source":
        order_by = f"{getattr(Organization, order_by)}".replace(
            "Organization.", ""
        )

    return text(f"{order_by} {get_order_by(order)}")


async def handle_search_params(
    cte: CTE, params: CompanySearchQuery, with_fuzzy_match=True
) -> Select:
    """
    This does not add limit, offset, order by param if params.free is defined
    """
    stmt = None

    if params.free:
        stmt = (
            add_fuzzy_match_to_stm(params.free, cte)
            if with_fuzzy_match
            else add_sub_string_match_to_stm(params.free, cte)
        )
    else:
        stmt = select(Organization, cte.c.source, cte.c.latest_reported_year)
        if params.name:
            name = normalize_text(params.name)
            stmt = stmt.where(Organization.legal_name.ilike(f"%{name}%"))
        if params.lei:
            statements = [
                Organization.lei.ilike(f"%{lei}") for lei in params.lei
            ]
            stmt = stmt.where(or_(*statements))

        if params.order_by:
            stmt = stmt.order_by(
                get_organization_order_by_text_stmt(
                    params.order_by, params.order
                )
            )
            # fix the problem of duplicates in different pages when sorting by source especially
            stmt = stmt.order_by(text("nz_id ASC"))

        if params.limit >= 0 and params.start >= 0:
            stmt = stmt.offset(params.start).limit(params.limit)

    if params.jurisdiction:
        statements = [
            Organization.jurisdiction == j for j in params.jurisdiction
        ]
        stmt = stmt.where(or_(*statements))
    if params.sics_sector:
        statements = [
            Organization.sics_sector.ilike(f"%{s}") for s in params.sics_sector
        ]
        stmt = stmt.where(or_(*statements))
    if params.source:
        stmt = stmt.where(cte.c.source.in_(params.source))
    if params.latest_reported_year:
        stmt = stmt.where(
            cte.c.latest_reported_year.in_(params.latest_reported_year)
        )

    return stmt


async def company_forms_latest(form: Table) -> CTE:
    ranked_submissions = (
        select(
            SubmissionObj.id,
            SubmissionObj.nz_id,
            SubmissionObj.data_source.label("source"),
            form.c.reporting_year.label("latest_reported_year"),
            SubmissionObj.lei.label("lei"),
            func.row_number()
            .over(
                partition_by=SubmissionObj.nz_id,
                order_by=form.c.reporting_year.desc(),
            )
            .label("rnk"),
        )
        .where(form.c.obj_id == SubmissionObj.id)
        .subquery()
    )

    return (
        select(
            ranked_submissions.c.id,
            ranked_submissions.c.source,
            ranked_submissions.c.latest_reported_year,
            ranked_submissions.c.lei,
            ranked_submissions.c.nz_id,
        )
        .where(ranked_submissions.c.rnk == 1)
        .cte("company_forms_latest")
    )


async def company_submissions_by_latest_year_fuzzy_match_query(
    static_cache: CoreMemoryCache,
    params: CompanySearchQuery,
) -> Select:
    form = await static_cache.get_form_table()
    cte = await company_forms_latest(form)
    companies_query = (
        await handle_search_params(
            cte,
            params,
        )
    ).join_from(cte, Organization, cte.c.nz_id == Organization.nz_id)

    if not params.free:
        return companies_query

    companies_matches = companies_query.subquery()
    omit_columns = ["alias", "score", "match_type"]
    selected_columns = [
        col.label(col.key)
        for col in companies_matches.c
        if col.key not in omit_columns
    ]

    scores_label = "max_score"

    stmt = (
        select(
            func.array_agg(companies_matches.c.alias).label("aliases"),
            func.max(companies_matches.c.score).label(scores_label),
            func.array_agg(companies_matches.c.match_type).label(
                "match_types"
            ),
            *selected_columns,
        )
        .group_by(*selected_columns)
        .order_by(text(f"{scores_label} DESC"))
    )

    if params.order_by:
        stmt = stmt.order_by(
            get_organization_order_by_text_stmt(params.order_by, params.order)
        )
        # fix the problem of duplicates in different pages when sorting by source especially
        stmt = stmt.order_by(text("nz_id ASC"))

    if params.limit >= 0 and params.start >= 0:
        stmt = stmt.offset(params.start).limit(params.limit)

    return stmt


async def companies_query_fuzzy_match(
    static_cache: CoreMemoryCache,
    params: CompanySearchQuery,
) -> Select:
    try:
        stmt = await company_submissions_by_latest_year_fuzzy_match_query(
            static_cache, params
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Database error: {exc}"},
        ) from exc
    return stmt


async def companies_query_sub_string_match(
    static_cache: CoreMemoryCache,
    params: CompanySearchQuery,
) -> Select:
    try:
        form = await static_cache.get_form_table()
        cte = await company_forms_latest(form)
        companies_query = (
            await handle_search_params(cte, params, False)
        ).join_from(cte, Organization, cte.c.nz_id == Organization.nz_id)

        if not params.free:
            return companies_query

        companies_matches = companies_query.subquery()
        omit_columns = ["alias", "match_type"]
        selected_columns = [
            col.label(col.key)
            for col in companies_matches.c
            if col.key not in omit_columns
        ]

        stmt = select(
            func.array_agg(companies_matches.c.alias).label("aliases"),
            func.array_agg(companies_matches.c.match_type).label(
                "match_types"
            ),
            *selected_columns,
        ).group_by(*selected_columns)

        if params.order_by:
            stmt = stmt.order_by(
                get_organization_order_by_text_stmt(
                    params.order_by, params.order
                )
            )
            # fix the problem of duplicates in different pages when sorting by source especially
            stmt = stmt.order_by(text("nz_id ASC"))

        if params.limit >= 0 and params.start >= 0:
            stmt = stmt.offset(params.start).limit(params.limit)

        return stmt

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Database error: {exc}"},
        ) from exc


def get_correct_company_item_type(obj_dict: dict, current_user: User):
    if current_user is None:
        return CompaniesListElement.model_validate(obj_dict)

    groups = [x.name for x in current_user.groups]
    if AuthRole.ADMIN.value in groups:
        return CompaniesListElementWithNonLeiIdentifiers.model_validate(
            obj_dict
        )

    return CompaniesListElement.model_validate(obj_dict)


def get_validated_company_item(o: Any, current_user: User | None):
    obj_dict = {
        **OrganizationService.filter_non_lei_identifiers_based_on_user_role(
            o.Organization,
            current_user,
        ).__dict__,
        "source": o.source,
        "latest_reported_year": o.latest_reported_year,
    }

    return get_correct_company_item_type(obj_dict, current_user)


def get_company_item(o: RowMapping, current_user: User | None):
    item_from_query = dict(o)

    item_from_query.pop("aliases")
    item_from_query.pop("match_types")
    source = item_from_query.pop("source")
    latest_reported_year = item_from_query.pop("latest_reported_year")

    item = OrganizationService.filter_non_lei_identifiers_based_on_user_role(
        Organization(**item_from_query),
        current_user,
    )

    return {
        **dict(item),
        "source": source,
        "latest_reported_year": latest_reported_year,
    }


@router.get("", response_model=CompaniesSpecificCriteriaList)
async def list_companies(
    background_tasks: BackgroundTasks,
    cache: Cache,
    static_cache: StaticCache,
    request: Request,
    db_manager: DbManager,
    current_user: User = Depends(get_current_user_or_none),
    # NOTE: this parameters are not used in the function, but are needed for right FE typing
    jurisdiction: str | None = None,
    name: str | None = None,
    lei: str | None = None,
    sics_sector: str | None = None,
    source: str | None = None,
    latest_reported_year: str | None = None,
    start: int = 0,
    limit: int = 10,
    order_by: str = "legal_name",
    order: str = "ASC",
    free: str | None = None,
):
    """
    Return the companies by specific criteria

    Parameters
    ----------
        jurisdiction - jurisdiction filter result
        name - company name, or a part of it
        latest_reported_year - latest year this company submitted data for
        sics_sector - SICS sector results
        source - data source results
        lei - Legal Entity Identifier (LEI), or a part of it
        start - starting index of the results
        limit - maximum number of results to return
        free - Search in specific fields when provided, ignore others (optional)
    Returns
    -------
        total - total number of result matching search criteria
        page - current page number
        page_size - number of items per page
        data - list companies matching search criteria
    """

    redis_key = consistent_hash(create_cache_key(request))
    companies_valued = await cache.get(redis_key)
    if companies_valued is not None:
        resp = orjson.loads(companies_valued)
        if len(resp.get("items", [])) > 0:
            try:
                companies_list = CompaniesSpecificCriteriaList(
                    **orjson.loads(companies_valued)
                )
                return companies_list
            except ValidationError as err:  # the cache is invalid
                background_tasks.add_task(cache.delete, redis_key)
                logger.error(err)

    async with db_manager.get_session() as _session:
        query = CompanySearchQuery.from_request(request)
        stmt = await companies_query_sub_string_match(static_cache, query)
        total = 0

        try:
            db_organizations = (await _session.execute(stmt)).mappings().all()

            # if there are not matches for sub string match, then use fuzzy matching
            if len(db_organizations) == 0:
                stmt = await companies_query_fuzzy_match(static_cache, query)
                db_organizations = (
                    (await _session.execute(stmt)).mappings().all()
                )

            count_stmt = select(func.count()).select_from(
                stmt.limit(None).offset(None).subquery()
            )
            total = (await _session.execute(count_stmt)).scalar()
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": f"Database error: {exc}"},
            ) from exc

        organizations = (
            [
                get_validated_company_item(o, current_user)
                for o in db_organizations
            ]
            if not query.free
            else [
                get_correct_company_item_type(
                    {
                        **get_company_item(o, current_user),
                        "alias": o.get("aliases")[0],
                        "is_alias_match": o.get("match_types")[0] == "alias",
                    },
                    current_user,
                )
                for o in db_organizations
            ]
        )

    page_size = min(len(db_organizations), query.limit)
    response = CompaniesSpecificCriteriaList(
        start=query.start,
        end=query.start + page_size,
        total=total or 0,
        items=organizations,
    )

    # add the response to the cache
    background_tasks.add_task(
        cache.set, redis_key, orjson.dumps(jsonable_encoder(response))
    )

    return response


@router.get("/download", response_class=FileResponse)
async def download_companies(
    static_cache: StaticCache,
    db_manager: DbManager,
    jurisdiction: str | None = None,
    name: str | None = None,
    latest_reported_year: str | None = None,
    lei: str | None = None,
    sics_sector: str | None = None,
    source: str | None = None,
    free: str | None = None,
):
    """
    Download the companies by specific criteria

    Parameters
    ----------
        jurisdiction - jurisdiction filter result
        name - company name, or a part of it
        latest_reported_year - reported year results
        lei - LEI results
        sics_sector - SICS sector results
        source - data source results
    Returns
    -------
        Download companies with specific criteria in CSV
    """
    try:
        # get result
        async with db_manager.get_session() as _session:
            search_query = CompanySearchQuery(
                jurisdiction=jurisdiction,
                name=name,
                lei=lei,
                sics_sector=sics_sector,
                source=source,
                latest_reported_year=latest_reported_year,
                free=free,
                limit=-1,
            )

            stmt = await companies_query_sub_string_match(
                static_cache, search_query
            )

            db_organizations = (await _session.execute(stmt)).mappings().all()

            # if there are not matches for sub string match, then use fuzzy matching
            if len(db_organizations) == 0:
                stmt = await companies_query_fuzzy_match(
                    static_cache, search_query
                )
                db_organizations = (
                    (await _session.execute(stmt)).mappings().all()
                )
            organizations = [
                CompaniesListElement.model_validate(
                    {
                        **(
                            object_as_dict(o.Organization)
                            if not search_query.free
                            else o
                        ),
                        "source": (
                            o.get("source") if search_query.free else o.source
                        ),
                        "latest_reported_year": (
                            o.get("latest_reported_year")
                            if search_query.free
                            else o.latest_reported_year
                        ),
                        "alias": (
                            o.get("aliases")[0] if search_query.free else None
                        ),
                        "is_alias_match": (
                            o.get("match_types")[0] == "alias"
                            if search_query.free
                            else None
                        ),
                    }
                )
                for o in db_organizations
            ]

            sics_sector_toggle = select(Config.value).where(
                Config.name == "data_download.exclude_classification"
            )
            result = await _session.execute(sics_sector_toggle)
            sics_sector_value = result.scalar()

            # create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False
            )
            # create and write to csv file
            with open(
                temp_file.name, "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Company",
                        "LEI",
                        "Jurisdiction",
                        "Latest Reported Year",
                        "SICS sector",
                        "Source",
                    ]
                )
                # Write every filtered organization from organizations
                for org in organizations:
                    writer.writerow(
                        [
                            org.legal_name,
                            org.lei,
                            org.jurisdiction,
                            org.latest_reported_year,
                            (
                                "SICS classification information not available"
                                " for download"
                                if sics_sector_value == "1"
                                else org.sics_sector
                            ),
                            org.source or "-",
                        ]
                    )
            companies_response = FileResponse(
                path=temp_file.name,
                media_type="application/octet-stream",
                filename="nzdpu_companies.csv",
            )

            return companies_response

    except HTTPException as exc:
        raise exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the request {exc}.",
        ) from exc


@router.get("/most-recent-reporting-year", response_model=MostRecentYear)
async def get_most_recent_reporting_year(
    background_tasks: BackgroundTasks,
    cache: Cache,
    request: Request,
    db_manager: DbManager,
    static_cache: StaticCache,
):
    """
    Return the most recent reporting year from all the submissions in the db


    Returns
    -------
        most_recent_reporting_year - Most recent reporting year
    """
    redis_key = create_cache_key(request)
    most_recent_year_cache = await cache.get(redis_key)

    if most_recent_year_cache is None:
        company_service = CompanyService(db_manager, static_cache)

        response = await company_service.get_most_recent_reporting_year()

        most_recent_year = MostRecentYear(most_recent_year=response)

        background_tasks.add_task(
            cache.set,
            redis_key,
            orjson.dumps(jsonable_encoder(most_recent_year)),
        )
        return most_recent_year

    return orjson.loads(most_recent_year_cache)


@router.get("/sources", response_model=DataSourcesResponse)
async def get_sources(
    background_tasks: BackgroundTasks,
    static_cache: StaticCache,
    cache: Cache,
    db_manager: DbManager,
    request: Request,
    nz_id: int | None = None,
) -> DataSourcesResponse:
    """
    Return the available sources for a company

    Returns
    -------
        sources - List of data sources
    """
    redis_key = create_cache_key(request)
    data_sources = await cache.get(redis_key)

    if data_sources is None:
        company_service = CompanyService(db_manager, static_cache)

        response = await company_service.get_sources(nz_id=nz_id)

        background_tasks.add_task(
            cache.set,
            redis_key,
            orjson.dumps(
                jsonable_encoder(DataSourcesResponse(data_sources=response))
            ),
        )
        return DataSourcesResponse(data_sources=response)

    return orjson.loads(data_sources)


@router.get("/jurisdictions", response_model=JurisdictionsResponse)
async def get_jurisdictions(
    static_cache: StaticCache,
    db_manager: DbManager,
    request: Request,
    cache: Cache,
    background_tasks: BackgroundTasks,
) -> JurisdictionsResponse:
    """
    Return the jurisdictions for all submissions

    Returns
    -------
        jurisdictions - List of jurisdictions
    """
    redis_key = create_cache_key(request)
    jurisdictions = await cache.get(redis_key)

    if jurisdictions:
        return orjson.loads(jurisdictions)

    company_service = CompanyService(db_manager, static_cache)

    data = await company_service.get_jurisdictions()
    background_tasks.add_task(
        cache.set,
        redis_key,
        orjson.dumps(jsonable_encoder(data)),
    )
    return data


@router.get("/reporting-years", response_model=ReportingYearsResponse)
async def get_reporting_years(
    static_cache: StaticCache,
    db_manager: DbManager,
    request: Request,
    cache: Cache,
    background_tasks: BackgroundTasks,
) -> ReportingYearsResponse:
    """
    Return the reported years for all submissions

    Returns
    -------
        reporting_years - List of reported years
    """
    redis_key = create_cache_key(request)
    reporting_years = await cache.get(redis_key)

    if reporting_years:
        return orjson.loads(reporting_years)

    company_service = CompanyService(db_manager, static_cache)

    data = await company_service.get_reporting_years()
    background_tasks.add_task(
        cache.set,
        redis_key,
        orjson.dumps(jsonable_encoder(data)),
    )
    return data


@router.get("/{nz_id}/reporting-years", response_model=ReportingYearsResponse)
async def get_reporting_years_by_nz_id(
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    request: Request,
    cache: Cache,
    background_tasks: BackgroundTasks,
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
    redis_key = create_cache_key(request)
    reporting_years = await cache.get(redis_key)

    if reporting_years:
        return orjson.loads(reporting_years)

    company_service = CompanyService(db_manager, static_cache)

    data = await company_service.get_reporting_years(nz_id=nz_id)
    background_tasks.add_task(
        cache.set,
        redis_key,
        orjson.dumps(jsonable_encoder(data)),
    )
    return data


@router.get("/data-models", response_model=DataModelsResponse)
async def get_data_models(
    static_cache: StaticCache,
    db_manager: DbManager,
    request: Request,
    cache: Cache,
    background_tasks: BackgroundTasks,
) -> DataModelsResponse:
    """
    Return the available data models for a company

    Parameters
    ----------
        nz_id - Unique identifier of the company

    Returns
    -------
        data_models - List of data models
    """
    redis_key = create_cache_key(request)
    data_models = await cache.get(redis_key)

    if data_models:
        return orjson.loads(data_models)

    company_service = CompanyService(db_manager, static_cache)

    data = await company_service.get_data_models()
    background_tasks.add_task(
        cache.set,
        redis_key,
        orjson.dumps(jsonable_encoder(data)),
    )

    return data


@router.get("/{nz_id}/history", response_model=CompanyEmissions)
async def get_company_emissions(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    model: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    source: int | None = None,
):
    """
    Return emissions reported by a company by year range and data model
    used.

    Parameters
    ----------
        nz_id - The company's NZ_ID.
        model - The used data model to filter on.
        year_from - The starting year range.
        year_to - The ending year range.
        source - <TBD>
    """

    s = perf_counter()

    async with db_manager.get_session() as _session:
        # construct query
        form_table = await static_cache.get_form_table()
        schema_service = SchemaService(static_cache=static_cache)
        forms_group_by = (
            await schema_service.get_group_by_forms_and_attributes()
        )

        stmt = (
            select(form_table.c.obj_id, form_table.c.reporting_year)
            .join(SubmissionObj, SubmissionObj.id == form_table.c.obj_id)
            .where(SubmissionObj.nz_id == nz_id, SubmissionObj.active == True)
        )

        if model is not None:
            stmt = stmt.where(form_table.c.data_model == model)
        if year_from is not None:
            stmt = stmt.where(form_table.c.reporting_year >= year_from)
        if year_to is not None:
            stmt = stmt.where(form_table.c.reporting_year <= year_to)

        # Ensuring results are ordered by year
        stmt = stmt.order_by(form_table.c.reporting_year.asc())

        # Execute the query
        result = await _session.execute(stmt)
        obj_ids = [row[0] for row in result]

        # get result
        aggregate_stmt = select(AggregatedObjectView).where(
            AggregatedObjectView.obj_id.in_(obj_ids)
        )
        # keep the order of the obj_ids in aggregate query
        for obj_id in obj_ids:
            aggregate_stmt = aggregate_stmt.order_by(
                text(f"obj_id={obj_id} DESC")
            )
        submission_objs = (await _session.scalars(aggregate_stmt)).all()
        history = []
        # submissions values must be gathered from different forms
        # and sub-forms
        for submission_obj in submission_objs:
            # so for each submission we found, we query its forms
            # and sub-forms
            submission = submission_obj.data
            if isinstance(submission, str):
                submission = orjson.loads(submission)
            submission_values = submission.get("values", {})

            reporting_year = submission_values.get("reporting_year")

            try:
                orgs = await static_cache.organizations()
                orgs[submission.get("nz_id", None)]
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"nz_id": f"No company found for given{nz_id=!r}"},
                ) from exc

            restated_fields_data_source = (
                await get_restated_fields_data_source(
                    submission.get("name"), _session
                )
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
                "restated_fields_data_source": restated_fields_data_source,
                "status": submission.get("status"),
                "values": submission_values,
                "units": submission.get("units"),
            }
            submission = SubmissionGet(**submission_data)
            history.append(
                {
                    "reporting_year": reporting_year,
                    "submission": submission,
                }
            )

        history_service = HistoryService()
        history_service.group_form_items(forms_group_by, history)

    logger.debug(f"Total time: {perf_counter() - s}")

    return CompanyEmissions(
        **{
            "nz_id": nz_id,
            "model": model,
            "source": source,
            "history": history,
        }
    )


@router.get("/lei={lei}/history/download", response_class=FileResponse)
@track_api_usage(api_endpoint=TrackingUrls.COMPANIES_HISTORY.value)
async def download_companies_history_by_lei(
    db_manager: DbManager,
    lei: str,
    current_user=Depends(
        RoleAuthorizationForMultipleAuth(
            [
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ],
            show_for_firebase=True,
        )
    ),
):
    company_service = CompanyService(db_manager, None)
    try:
        result = await company_service.download_companies("lei", lei)
    except GoogleAPICallError as exc:
        raise HTTPException(
            status_code=exc.code, detail=exc.response.text
        ) from exc
    return StreamingResponse(
        result.file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        },
    )


@router.get("/{nz_id}/history/download", response_class=FileResponse)
@track_api_usage(api_endpoint=TrackingUrls.COMPANIES_HISTORY.value)
async def download_companies_history(
    db_manager: DbManager,
    nz_id: int,
    current_user=Depends(
        RoleAuthorizationForMultipleAuth(
            [
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ],
            show_for_firebase=True,
        )
    ),
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

    company_service = CompanyService(db_manager, None)
    try:
        result = await company_service.download_companies("nz_id", nz_id)
    except GoogleAPICallError as exc:
        raise HTTPException(
            status_code=exc.code, detail=exc.response.text
        ) from exc
    return StreamingResponse(
        result.file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={result.filename}"
        },
    )


@router.get("/{nz_id}/disclosures", response_model=CompanyDisclosures)
async def get_company_disclosures(
    db_manager: DbManager,
    static_cache: StaticCache,
    nz_id: int,
    model: str | None = None,
    limit: int | None = None,
    sort_by: DisclosureSortByEnum | None = None,
    start: int = 0,
) -> dict[str, int | str | list[dict]]:
    """
    Return the company's disclosures by specific criteria

    Parameters
    ----------
        nz_id - Unique identifier of the company
        model - Data model used for the disclosure
        sort_by - Sort by specified criteria
        start, limit - Pagination parameters

    Returns
    -------
        Details of the requested disclosure
    """

    async with db_manager.get_session() as _session:
        # get organization by LEI
        orgs = await static_cache.organizations()
        org = orgs.get(nz_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"lei": "No organization found for the provided LEI."},
            )

        nzdpu_form = await static_cache.get_form_table()
        sql_alchemy_query = (
            select(
                SubmissionObj.id.label("submission_id"),
                nzdpu_form.c.data_model.label("model"),
                nzdpu_form.c.reporting_year.label("year"),
                nzdpu_form.c.reporting_datetime.label("last_updated"),
            )
            .join(
                nzdpu_form,
                nzdpu_form.c.obj_id == SubmissionObj.id,
            )
            .where(SubmissionObj.nz_id == nz_id, SubmissionObj.active == True)
        )

        count_query = (
            select(func.count())
            .select_from(SubmissionObj)
            .join(nzdpu_form, nzdpu_form.c.obj_id == SubmissionObj.id)
            .where(SubmissionObj.nz_id == nz_id, SubmissionObj.active == True)
        )

        if model:
            sql_alchemy_query = sql_alchemy_query.where(
                nzdpu_form.c.data_model == model
            )
            count_query = count_query.where(nzdpu_form.c.data_model == model)

        if sort_by:
            if (
                sort_by == DisclosureSortByEnum.MOST_RECENT_YEAR
                and DisclosureSortByEnum.MOST_RECENT_YEAR == "most_recent_year"
            ):
                sql_alchemy_query = sql_alchemy_query.order_by(
                    nzdpu_form.c.reporting_year.desc()
                )
            else:
                sql_alchemy_query = sql_alchemy_query.order_by(
                    nzdpu_form.c.reporting_year.asc()
                )
        else:  # enter default ORDER BY: PostgreSQL LIMIT needs one
            sql_alchemy_query = sql_alchemy_query.order_by(
                nzdpu_form.c.reporting_year.asc()
            )

        if limit:
            sql_alchemy_query = sql_alchemy_query.limit(limit)
        if start:
            sql_alchemy_query = sql_alchemy_query.offset(start)

        results = [
            # link fields to values
            dict(zip(row._fields, row))
            for row in await _session.execute(sql_alchemy_query)
        ]
        # Execute the count query
        total_records = await _session.scalar(count_query)
        return {
            "start": start,
            "end": limit or len(results),
            "total": total_records,
            "nz_id": nz_id,
            "items": results,
        }


@router.get(
    "/{nz_id}/disclosure-details", response_model=DisclosureDetailsResponse
)
async def get_disclosure_details(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    year: int,
    model: str | None = None,
    source: str | None = None,
):
    """
    Return the details of the requested disclosure.

    Parameters
    ----------
        nz_id - Unique identifier of the company
        model - Data model used for the disclosure
        year - Reporting year
        source - Data source

    Returns
    -------
        Details of the requested disclosure
    """

    async with db_manager.get_session() as _session:
        # construct list of user ids for raw SQL query
        nzdpu_form = await static_cache.get_form_table()

        sql_alchemy_query = (
            select(
                SubmissionObj.id,
                nzdpu_form.c.reporting_datetime,
                SubmissionObj.active,
            )
            .join(nzdpu_form, nzdpu_form.c.obj_id == SubmissionObj.id)
            .where(
                SubmissionObj.nz_id == nz_id,
                nzdpu_form.c.reporting_year == year,
            )
            .order_by(text("revision DESC"))
        )

        if model:
            sql_alchemy_query = sql_alchemy_query.where(
                nzdpu_form.c.data_model == model
            )
        if source:
            sql_alchemy_query = sql_alchemy_query.where(
                SubmissionObj.data_source == source
            )

        sql_alchemy_query = sql_alchemy_query.order_by(SubmissionObj.id.asc())

        db_results = (await _session.execute(sql_alchemy_query)).all()

        all_obj_ids = []
        active_obj_ids = []
        submission_original_reporting_datetime = None
        for obj_id, reporting_datetime, is_active in db_results:
            all_obj_ids.append(obj_id)

            if is_active:
                active_obj_ids.append(obj_id)

            if submission_original_reporting_datetime is None:
                submission_original_reporting_datetime = reporting_datetime

        if not active_obj_ids:
            raise HTTPException(
                status_code=404,
                detail={
                    "submission": (
                        "No active submission found for the given parameters."
                    )
                },
            )

        loader = SubmissionLoader(_session, static_cache, cache)

        results: list[SubmissionGet] = [
            await loader.load(obj_id, use_aggregate=True)
            for obj_id in active_obj_ids
        ]
        if not results:
            raise HTTPException(
                status_code=404,
                detail={
                    "global": "No disclosures found for the given parameters."
                },
            )

        if len(results) > 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "global": (
                        "Multiple disclosures found for the given parameters."
                    )
                },
            )
        submission = results[0]  # it's already asserted as a single element

        if submission:
            submission.last_updated = submission.values.get(
                "reporting_datetime"
            )

        restatement_service = RestatementService(db_manager)
        restatements = (
            await restatement_service.get_restatements_by_submission_ids(
                all_obj_ids
            )
        )

        restated_fields_last_updated = {}
        for restatement in restatements:
            restated_fields_last_updated[restatement.attribute_name] = (
                restatement.reporting_datetime
            )
        # generate computed units
        submission.restated_fields_last_updated = restated_fields_last_updated
        submission.originally_created_on = (
            submission_original_reporting_datetime
        )
        submission.restated_fields_data_source = (
            await get_restated_fields_data_source(submission.name, _session)
        )

        return submission


@router.get("/{nz_id}/restatements", response_model=RestatementGet)
async def list_restatements(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    attribute: str,
    year: int,
):
    """
    Return the restatements by specific criteria

    Parameters
    ----------
        nz_id - NZ_ID of the company
        attribute - name of the attribute we want to fetch restatements of

    Returns
    -------
        lei - legal entity identifier of the company
        attribute - name and prompt from attribute we fetch restatements of
        original - first submission created
        restatements - list of restatements
    """

    # get result
    async with db_manager.get_session() as _session:
        attribute_path = AttributePathsModel.unpack_field_path(attribute)
        # load attribute prompt
        attribute_prompt = await get_attribute_prompt_from_path(
            attribute_path, static_cache
        )
        # get all submissions
        submission_ids = list(
            (
                await _session.scalars(
                    select(SubmissionObj.id)
                    .where(SubmissionObj.nz_id == nz_id)
                    .order_by(SubmissionObj.revision)
                )
            ).all()
        )
        if not submission_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "nz_id": f"No submissions found for given nz_id '{nz_id}'"
                },
            )
        # get restatements from db
        nzdpu_form = await static_cache.get_form_table()
        try:
            form_query = (
                select(nzdpu_form.c.obj_id, nzdpu_form.c.reporting_year)
                .distinct()
                .join(
                    SubmissionObj,
                    SubmissionObj.id == nzdpu_form.c.obj_id,
                )
                .where(
                    and_(
                        nzdpu_form.c.obj_id.in_(submission_ids),
                        SubmissionObj.revision == 1,
                        nzdpu_form.c.reporting_year == year,
                    )
                )
                .order_by(nzdpu_form.c.reporting_year.asc())
            )
        except Exception as e:
            raise HTTPException(
                detail=f"Error fetching restatements: {str(e)}",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from e

        form_fields = await _session.execute(form_query)
        form_res = form_fields.all()
        # Extract the values into a list
        submission_ids_with_revision_one = [row[0] for row in form_res]
        submission_ids_with_revision_one.sort()
        db_restatements = list(
            (
                await _session.scalars(
                    (
                        select(Restatement)
                        .where(Restatement.obj_id.in_(submission_ids))
                        .where(Restatement.attribute_name == attribute)
                    )
                )
            ).all()
        )
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        if submission_ids_with_revision_one:
            # get data from first submission
            original = await get_original_value(
                submission_loader=submission_loader,
                submission_ids=submission_ids_with_revision_one,
                attribute_path=attribute_path,
                year=year,
            )
            restatements = await process_restatements(
                submission_loader=submission_loader,
                db_restatements=db_restatements,
                attribute_path=attribute_path,
                year=year,
            )

            response = RestatementGet(
                nz_id=nz_id,
                attribute=RestatementAttributePrompt(
                    name=attribute, prompt=attribute_prompt.value
                ),
                original=original,
                restatements=restatements,
            )
            return response
        response = RestatementGet(
            nz_id=nz_id,
            attribute=RestatementAttributePrompt(
                name=attribute, prompt=attribute_prompt.value
            ),
            original=RestatementOriginal(
                **{
                    "reporting_year": 0,
                    "reported_on": None,
                    "value": None,
                    "disclosure_source": None,
                }
            ),
            restatements=[],
        )
        return response


@router.get(
    "/{nz_id}/targets", tags=["companies"], response_model=TargetsResponse
)
async def get_targets(
    db_manager: DbManager,
    static_cache: StaticCache,
    cache: Cache,
    background_tasks: BackgroundTasks,
    request: Request,
    nz_id: int,
    active: bool | None = None,
    source: str | None = None,
):
    """get_targets _summary_

    :param bool active: _description_, defaults to None
    :returns: _
    """
    redis_key = create_cache_key(request)

    targets = await cache.get(redis_key)

    if targets:
        return orjson.loads(targets)

    try:
        company_service = CompanyService(db_manager, static_cache)
        source_param = source

        sources = await company_service.get_sources(order_desc=True)
        abs_targets = await company_service.get_absolute_targets(
            active, nz_id, source_param
        )
        int_targets = await company_service.get_intensity_targets(
            active, nz_id, source_param
        )

        targets_by_source: list[TargetBySource] = []
        # group targets by source
        for source in sources:
            if source_param and source_param != source:
                continue
            abs_targets_filtered = list(
                filter(lambda p: p.data_source == source, abs_targets)
            )

            abs_targets_data = [
                Target(
                    category="absolute",
                    id=abs_targets_filtered[i].tgt_abs_id,
                    name=abs_targets_filtered[i].tgt_abs_name,
                    target_base_year=abs_targets_filtered[i].tgt_abs_base_year,
                    target_year_set=abs_targets_filtered[i].tgt_abs_year_set,
                    target_coverage_scope=str(
                        abs_targets_filtered[i].tgt_abs_cvg_scope
                    ),
                    active=(
                        True
                        if abs_targets_filtered[i].tgt_abs_status.lower()
                        == "active"
                        else False
                    ),
                    last_updated=abs_targets_filtered[i].reporting_datetime,
                    position=i,
                )
                for i in range(0, len(abs_targets_filtered))
            ]
            int_targets_filtered = list(
                filter(lambda p: p.data_source == source, int_targets)
            )
            int_targets_data = [
                Target(
                    category="intensity",
                    id=int_targets_filtered[i].tgt_int_id,
                    name=int_targets_filtered[i].tgt_int_name,
                    target_base_year=int_targets_filtered[i].tgt_int_base_year,
                    target_year_set=int_targets_filtered[i].tgt_int_year_set,
                    target_coverage_scope=str(
                        int_targets_filtered[i].tgt_int_cvg_scope
                    ),
                    active=(
                        True
                        if int_targets_filtered[i].tgt_int_status.lower()
                        == "active"
                        else False
                    ),
                    last_updated=int_targets_filtered[i].reporting_datetime,
                    position=i,
                )
                for i in range(0, len(int_targets_filtered))
            ]
            targets_by_source.append(
                TargetBySource(
                    source=source,
                    items=abs_targets_data + int_targets_data,
                )
            )

        # sort targets by specific criteria
        for target_by_source in targets_by_source:
            target_by_source.items = sorted(
                target_by_source.items,
                key=lambda x: (
                    x.name,
                    x.target_year_set,
                    x.target_base_year or "",
                    x.target_coverage_scope or "",
                ),
            )

    except Exception as e:
        raise HTTPException(
            status_code=422, detail=f"Error retrieving targets: {e}"
        ) from e

    final_result = TargetsResponse(targets=targets_by_source)

    background_tasks.add_task(
        cache.set,
        redis_key,
        orjson.dumps(jsonable_encoder(final_result)),
    )

    return final_result


@router.get(
    "/{nz_id}/targets/progress",
    tags=["companies"],
    response_model=TargetsProgressResponse,
)
async def get_targets_progress(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    model: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    data_sources: str | None = None,
):
    """
    Return all targets progress with filters.

    Parameters
    ----------
        nz_id (required) - the nzdpu identifier
        model (optional) - the data model
        year_start (optional) - year from
        year_end (optional) - year end
        data_sources (optional) - the data source from nzdpu form

    Returns
    -------
        the two categories for absolute and intensity targets
    """
    async with db_manager.get_session() as _session:
        try:
            # construct query
            nzdpu_form_table = await static_cache.get_form_table()
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
            if model is not None:
                stmt = stmt.where(nzdpu_form_table.c.data_model == model)
            if year_start is not None:
                stmt = stmt.where(
                    nzdpu_form_table.c.reporting_year >= year_start
                )
            if year_end is not None:
                stmt = stmt.where(
                    nzdpu_form_table.c.reporting_year <= year_end
                )
            if data_sources is not None:
                stmt = stmt.where(SubmissionObj.data_source == data_sources)
            # Execute the query
            result = await _session.execute(stmt)

            submission_loader = SubmissionLoader(_session, static_cache, cache)
            # check which submissions have target_progress
            submissions_list = []
            for sub_id, tgt_abs_value, tgt_int_value in result.fetchall():
                if (
                    tgt_abs_value is not None
                    and tgt_abs_value not in NullTypeState.values()
                ) or (
                    tgt_int_value is not None
                    and tgt_int_value not in NullTypeState.values()
                ):
                    submissions_list.append(
                        await submission_loader.load(
                            sub_id, use_aggregate=True
                        )
                    )
            if submissions_list:
                targets_progress_result = []
                for submission in submissions_list:
                    last_updated = submission.values.get("reporting_datetime")
                    for idx, target_abs in enumerate(
                        submission.values.get("tgt_abs_progress_dict")
                    ):
                        tgt_abs_progress_dict = (
                            await process_target_progress_categories(
                                submission.values.get("tgt_abs_dict")[idx],
                                target_abs,
                                submission.data_source,
                                "tgt_abs_id_progress",
                                _session,
                                static_cache,
                                last_updated,
                            )
                        )
                        if tgt_abs_progress_dict:
                            targets_progress_result.append(
                                tgt_abs_progress_dict
                            )
                    for idx, target_int in enumerate(
                        submission.values.get("tgt_int_progress_dict")
                    ):
                        tgt_int_progress_dict = (
                            await process_target_progress_categories(
                                submission.values.get("tgt_int_dict")[idx],
                                target_int,
                                submission.data_source,
                                "tgt_int_id_progress",
                                _session,
                                static_cache,
                                last_updated,
                            )
                        )
                        if tgt_int_progress_dict:
                            targets_progress_result.append(
                                tgt_int_progress_dict
                            )
            else:
                raise HTTPException(
                    status_code=404, detail="Targets progress not found"
                )

        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Error retrieving targets progress: {e}",
            ) from e
    target_progress_data = {
        "targets_progress": targets_progress_result,
    }
    return target_progress_data


@router.get(
    path="/{nz_id}/targets/progress/{tgt_id}",
    tags=["companies"],
    response_model=TargetsProgressSingleResponse,
)
async def get_target_progress_by_id(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    background_tasks: BackgroundTasks,
    request: Request,
    nz_id: int,
    tgt_id: str,
    tgt_category: TargetCategory,
    data_source: str | None = None,
):
    """
    Return single targets progress with filters.

    Parameters
    ----------
        nz_id (required) - the nzdpu identifier
        tgt_id (required) - the target identifier
        tgt_category (required) - the target category

    Returns
    -------
        the single target progress
    """
    redis_key = create_cache_key(request)
    cached_data = await cache.get(redis_key)

    if cached_data is not None:
        try:
            target_progress = TargetsProgressSingleResponse(
                **json.loads(cached_data)
            )
            return target_progress
        except ValidationError as err:  # the cache is invalid
            background_tasks.add_task(cache.delete, redis_key)
            logger.error(err)
    try:
        company_service = CompanyService(db_manager, static_cache)
        tgt_progress_dict = await company_service.get_single_target_progress(
            nz_id=nz_id,
            tgt_id=tgt_id,
            tgt_category=tgt_category,
            cache=cache,
            data_source=data_source,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Error retrieving targets progress: {e}",
        ) from e
    target_progress_data = {
        "targets_progress": tgt_progress_dict,
    }
    # Add the response to the cache
    background_tasks.add_task(
        cache.set,
        redis_key,
        json.dumps(jsonable_encoder(target_progress_data)),
    )
    return target_progress_data


@router.get(
    "/{nz_id}/targets/{tgt_id}",
    tags=["companies"],
    response_model=GetTargetById,
)
async def get_targets_by_id(
    static_cache: StaticCache,
    cache: Cache,
    db_manager: DbManager,
    nz_id: int,
    tgt_id: str,
    data_source: str | None = None,
):
    """
    Return the two categories for absolute and intensity targets.

    Parameters
    ----------
        nz_id (required) - the nzdpu identifier
        tgt_id (required) - the target identifier

    Returns
    -------
        the two categories for absolute and intensity targets
    """
    async with db_manager.get_session() as _session:
        tgt_category = tgt_id[:3].lower()
        tgt_form = f"tgt_{tgt_category}_dict_form_heritable"
        tgt_form_id = f"tgt_{tgt_category}_id"
        tgt_values = f"tgt_{tgt_category}_dict"
        tgt_form_table = await static_cache.get_form_table(tgt_form)

        # load submission objs list
        stmt = (
            select(SubmissionObj.id)
            .join(tgt_form_table, tgt_form_table.c.obj_id == SubmissionObj.id)
            .where(
                SubmissionObj.nz_id == nz_id,
                text(f"{tgt_form_id} = :tgt_id")
                .bindparams(tgt_id=tgt_id)
                .compile(compile_kwargs={"literal_binds": True})
                .statement,
            )
            .order_by(SubmissionObj.revision.desc())
            .order_by(SubmissionObj.id.asc())
        )

        if data_source:
            stmt = stmt.where(SubmissionObj.data_source == data_source)

        submissions_objs = list(await _session.scalars(stmt))

        if len(submissions_objs) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"Submission": f"Submission with {nz_id} not found"},
            )

        submission_id = submissions_objs[0]

        # load submissions
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submission = await submission_loader.load(
            submission_id, use_aggregate=True
        )
        last_updated = submission.values.get("reporting_datetime")
        result_data = {
            "data_source": submission.data_source,
            "reporting_year": submission.values.get("reporting_year"),
        }
        # get specific target with target id
        targets = next(
            (
                {
                    k: v
                    for k, v in d.items()
                    if not k.endswith("_prompt")
                    and k not in ["id", "obj_id", "value_id"]
                }
                for d in submission.values.get(tgt_values)
                if d[tgt_form_id] == f"{tgt_id}"
            ),
            None,
        )
        result_data.update(targets)
        full_data = {}
        full_data_units = {}

        company_service = CompanyService(db_manager, static_cache)
        position = await company_service.get_target_position(
            nz_id=nz_id,
            tgt_id=tgt_id,
            tgt_category=tgt_category,
            data_source=data_source,
        )

        restatement_service = RestatementService(db_manager=db_manager)
        restatements = (
            await restatement_service.get_restatements_by_submission_ids(
                submissions_objs
            )
        )
        attribute_name_last_update_dict = (
            restatement_service.get_attribute_name_last_update_mapper_for_tgt(
                restatements, position=position
            )
        )
        attribute_name_last_source_dict = (
            restatement_service.get_attribute_name_last_source_mapper_for_tgt(
                restatements, position=position
            )
        )

        # format response for specific target
        for key, value in result_data.items():
            full_data[key] = (
                value
                if key in ["data_source", "reporting_year", tgt_form_id]
                else {
                    "value": value,
                    "last_update": (
                        attribute_name_last_update_dict[key]
                        if key in attribute_name_last_update_dict
                        else last_updated
                    ),
                    "last_source": (
                        attribute_name_last_source_dict[key]
                        if key in attribute_name_last_source_dict
                        else submission.data_source
                    ),
                }
            )
            # format units and dynamic units
            full_data_units[key] = await format_units(
                result_data, key, _session, static_cache
            )
        # Create an instance of GetTargetById and set its attributes
        response_model = GetTargetById(
            absolute=AbsoluteDataModelWrapper(
                tgt_abs_dict=(
                    AbsoluteDataModel(**full_data)
                    if tgt_category == "abs"
                    else None
                ),
                units={
                    "tgt_abs_dict": (
                        full_data_units if tgt_category == "abs" else None
                    )
                },
            ),
            intensity=IntensityDataModelWrapper(
                tgt_int_dict=(
                    IntensityDataModel(**full_data)
                    if tgt_category == "int"
                    else None
                ),
                units={
                    "tgt_int_dict": (
                        full_data_units if tgt_category == "int" else None
                    )
                },
            ),
        )

        return response_model


def build_validation_dict(
    prefix: str,
    rec: object,
    original_reporting_datetime: datetime,
) -> dict:
    """
    Helper function to build the validation dictionary for both int and abs types.
    :param prefix: Prefix for the columns (either 'tgt_int_' or 'tgt_abs_')
    :param rec: The record object containing the data
    :param original_reporting_datetime: The original datetime to set for last_updated fields
    :return: A dictionary representing the validation information
    """
    return {
        f"valid_tgt_{prefix}_provider": {
            "value": getattr(rec, f"valid_tgt_{prefix}_provider"),
            "last_updated": original_reporting_datetime,
        },
        f"valid_tgt_{prefix}_source": {
            "value": getattr(rec, f"valid_tgt_{prefix}_source"),
            "last_updated": original_reporting_datetime,
        },
        f"valid_tgt_{prefix}_statement": {
            "value": getattr(rec, f"valid_tgt_{prefix}_statement"),
            "last_updated": original_reporting_datetime,
        },
        f"rationale_tgt_{prefix}_valid_non_disclose": {
            "value": getattr(
                rec, f"rationale_tgt_{prefix}_valid_non_disclose"
            ),
            "last_updated": original_reporting_datetime,
        },
    }


@router.get(
    "/{nz_id}/targets/{tgt_id}/validations",
    tags=["companies"],
    response_model=TargetsValidationSchema,
)
async def get_target_validation_by_company(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    nz_id: int,
    tgt_id: str,
    data_source: str | None = None,
):
    """get_target_validation_by_company _summary_
    :param Session session: _description_
    :param str lei: _description_
    :param str tgt_id: _description_
    :returns: _
    Target validation by company
    """
    tgt_category = tgt_id[:3].lower()
    target_validation_result = None
    async with db_manager.get_session() as _session:
        target_validation_not_found = HTTPException(
            status_code=404,
            detail="Target validation company progress not found",
        )

        try:
            # Fetch the tables for int and abs
            tgt_int_valid_dict_form_heritable = (
                await static_cache.get_form_table(
                    "tgt_int_valid_dict_form_heritable"
                )
            )

            tgt_abs_valid_dict_form_heritable = (
                await static_cache.get_form_table(
                    "tgt_abs_valid_dict_form_heritable"
                )
            )

            # Construct both queries (int and abs)
            stmt_int = (
                select(
                    SubmissionObj.id,
                    SubmissionObj.data_source,
                    SubmissionObj.created_on,
                    SubmissionObj.name,
                    tgt_int_valid_dict_form_heritable.c.tgt_int_id_valid,
                    tgt_int_valid_dict_form_heritable.c.valid_tgt_int_provider,
                    tgt_int_valid_dict_form_heritable.c.valid_tgt_int_source,
                    tgt_int_valid_dict_form_heritable.c.valid_tgt_int_statement,
                    tgt_int_valid_dict_form_heritable.c.rationale_tgt_int_valid_non_disclose,
                )
                .join(
                    tgt_int_valid_dict_form_heritable,
                    SubmissionObj.id
                    == tgt_int_valid_dict_form_heritable.c.obj_id,
                )
                .where(
                    SubmissionObj.nz_id == nz_id,
                    text(
                        "(tgt_int_valid_dict_form_heritable.tgt_int_id_valid).value = :tgt_id"
                    )
                    .bindparams(tgt_id=tgt_id)
                    .compile(compile_kwargs={"literal_binds": True})
                    .statement,
                )
            )
            if data_source:
                stmt_int = stmt_int.where(
                    SubmissionObj.data_source == data_source
                )
            stmt_int = stmt_int.order_by(SubmissionObj.id.asc())

            stmt_abs = (
                select(
                    SubmissionObj.id,
                    SubmissionObj.data_source,
                    SubmissionObj.created_on,
                    SubmissionObj.name,
                    tgt_abs_valid_dict_form_heritable.c.tgt_abs_id_valid,
                    tgt_abs_valid_dict_form_heritable.c.valid_tgt_abs_provider,
                    tgt_abs_valid_dict_form_heritable.c.valid_tgt_abs_source,
                    tgt_abs_valid_dict_form_heritable.c.valid_tgt_abs_statement,
                    tgt_abs_valid_dict_form_heritable.c.rationale_tgt_abs_valid_non_disclose,
                )
                .join(
                    tgt_abs_valid_dict_form_heritable,
                    SubmissionObj.id
                    == tgt_abs_valid_dict_form_heritable.c.obj_id,
                )
                .where(
                    SubmissionObj.nz_id == nz_id,
                    tgt_abs_valid_dict_form_heritable.c.tgt_abs_id_valid
                    == tgt_id,
                )
            )
            if data_source:
                stmt_abs = stmt_abs.where(
                    SubmissionObj.data_source == data_source
                )
            stmt_abs = stmt_abs.order_by(SubmissionObj.id.asc())

            result_int = await _session.execute(stmt_int)
            result_abs = await _session.execute(stmt_abs)

            result_int_fetched = result_int.fetchall()
            result_abs_fetched = result_abs.fetchall()

            if result_int_fetched:
                result = result_int_fetched
            else:
                result = result_abs_fetched

            if not result:
                raise target_validation_not_found

            original_reporting_datetime = None
            all_submission_ids = []
            target_validation_result = {}
            category = None

            for single_rec in result:
                source = single_rec.data_source

                # Get reporting year info
                nzdpu_form_table = await static_cache.get_form_table()
                stmt = select(
                    nzdpu_form_table.c.reporting_year,
                    nzdpu_form_table.c.reporting_datetime,
                ).where(nzdpu_form_table.c.obj_id == single_rec.id)
                result = (await _session.execute(stmt)).first()

                if not result:
                    continue

                reporting_year = result[0]

                reporting_datetime = result[1]

                original_reporting_datetime = reporting_datetime

                all_submission_ids.append(single_rec.id)

                # Add validation results for both int and abs
                target_validation_result = {
                    "source": source,
                    "last_update": reporting_datetime,
                    "reporting_year": reporting_year,
                }

                # Add int_validation only if result_abs is not empty
                if result_int_fetched:
                    target_validation_result["values"] = build_validation_dict(
                        "int", single_rec, original_reporting_datetime
                    )
                    category = TargetCategory.INTENSITY
                elif result_abs_fetched:
                    target_validation_result["values"] = build_validation_dict(
                        "abs", single_rec, original_reporting_datetime
                    )
                    category = TargetCategory.ABSOLUTE

        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Error retrieving target validation company: {e}",
            ) from e

        if not target_validation_result:
            raise target_validation_not_found

        target_validation_result["originally_created_on"] = (
            original_reporting_datetime
        )

        company_service = CompanyService(db_manager, static_cache)
        position = await company_service.get_target_position(
            nz_id=nz_id,
            tgt_id=tgt_id,
            tgt_category=tgt_category,
            data_source=data_source,
        )

        # Restatement logic for both int and abs
        restatement_service = RestatementService(db_manager=db_manager)
        restatements = (
            await restatement_service.get_restatements_by_submission_ids(
                all_submission_ids
            )
        )

        attribute_name_last_update_dict = (
            restatement_service.get_attribute_name_last_update_mapper_for_tgt(
                restatements, position=position
            )
        )

        attribute_name_last_source_dict = (
            restatement_service.get_attribute_name_last_source_mapper_for_tgt(
                restatements, position=position
            )
        )

        restated = False
        values = target_validation_result["values"]
        for key, _ in values.items():
            target_validation_result["values"][key]["last_source"] = (
                attribute_name_last_source_dict[key]
                if key in attribute_name_last_source_dict
                else source
            )
            target_validation_result["values"][key]["last_updated"] = (
                attribute_name_last_update_dict[key]
                if key in attribute_name_last_update_dict
                else original_reporting_datetime
            )
            if (
                key in attribute_name_last_source_dict
                and key in attribute_name_last_update_dict
            ):
                restated = True

        target_validation_result["restated"] = restated

    target_validation_response = TargetsValidationSchema(
        **target_validation_result, category=category
    )
    return target_validation_response


@router.get(
    "/{nz_id}/disclosure-details/restated-fields",
    response_model=CompanyRestatementsResponseModel,
)
async def get_restated_fields(
    db_manager: DbManager, static_cache: StaticCache, nz_id: int, year: int
) -> CompanyRestatementsResponseModel:
    async with db_manager.get_session() as _session:
        form_table = await static_cache.get_form_table()

        stmt = (
            select(
                SubmissionObj.name,
                Restatement.attribute_name,
            )
            .join(
                form_table,
                form_table.c.obj_id == SubmissionObj.id,
            )
            .outerjoin(
                Restatement,
                Restatement.obj_id == SubmissionObj.id,
            )
            .where(
                SubmissionObj.nz_id == nz_id,
                form_table.c.reporting_year == year,
            )
            .order_by(
                SubmissionObj.id.asc(),
            )
        )
        result = list((await _session.execute(stmt)).all())
        # query result checks
        # check result not empty
        if not result:
            return CompanyRestatementsResponseModel(
                name=None,
                fields=[],
            )
        # check same submission for all results
        if not all([row[0] == result[0][0] for row in result]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "global": (
                        f"Multiple submissions found for {nz_id=} and {year=}"
                    )
                },
            )

        return CompanyRestatementsResponseModel(
            name=result[0][0],
            fields=list({row[1] for row in result if row[1] is not None}),
        )


async def get_original_value(
    submission_loader: SubmissionLoader,
    submission_ids: list[int],
    attribute_path: AttributePathsModel,
    year: int | None = None,
) -> RestatementOriginal | None:
    """
    Get original value from submission where revision = 1
    """
    # get data from first submission
    submission = await submission_loader.load(
        submission_id=submission_ids[0],  # revision = 1
        use_aggregate=True,
    )
    reporting_year = submission.values[FormMeta.f_reporting_year]

    reporting_datetime = submission.values.get(
        "reporting_datetime", submission.created_on
    )

    if year is None:
        return RestatementOriginal(
            reporting_year=reporting_year,
            reported_on=reporting_datetime,
            value=submission_loader.return_value(
                path=attribute_path, values=submission.values
            )
            or {},
            disclosure_source=submission.data_source or -1,
        )
    if year == reporting_year:
        return RestatementOriginal(
            reporting_year=reporting_year,
            reported_on=reporting_datetime,
            value=submission_loader.return_value(
                path=attribute_path, values=submission.values
            )
            or {},
            disclosure_source=submission.data_source or -1,
        )
    return None


async def process_restatements(
    submission_loader: SubmissionLoader,
    db_restatements: list[Restatement],
    attribute_path: AttributePathsModel,
    year: int | None = None,
):
    """
    Process restatements
    """
    restatements = []

    for restatement_db in db_restatements:
        submission = await submission_loader.load(
            submission_id=restatement_db.obj_id,
            use_aggregate=True,
        )
        reporting_year = submission.values[FormMeta.f_reporting_year]

        if year and year == reporting_year:
            restatements.append(
                RestatementList(
                    reporting_year=reporting_year,
                    reported_on=restatement_db.reporting_datetime,
                    value=submission_loader.return_value(
                        attribute_path, submission.values
                    )
                    or {},
                    reason=restatement_db.reason_for_restatement or "",
                    disclosure_source=restatement_db.data_source or -1,
                )
            )

    return restatements
