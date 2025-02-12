"""Module for Search API."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from google.cloud import storage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.settings as settings
from app.service.core.errors import SubmissionError
from app.service.core.search import QueryDSLTransformer, SubmissionFinder
from app.service.exports.constants import MAXIMUM_DOWNLOAD_COMPANIES_EXCEL
from app.service.exports.errors import EXCEL_DOWNLOAD_TOO_MANY_COMPANIES
from app.service.exports.exceptions import DownloadExceedMaximumException
from app.service.search_service import SearchService

from ..db.models import (
    AuthRole,
    Config,
    ConfigProperty,
    TableDef,
    TableView,
    User,
)
from ..dependencies import (
    Cache,
    DbManager,
    RoleAuthorizationForMultipleAuth,
    StaticCache,
)
from ..loggers import get_nzdpu_logger
from ..schemas.search import (
    DownloadExceedResponse,
    SearchQuery,
    SearchResponse,
)
from ..schemas.tracking import TrackingUrls
from ..service.exports.search_download import SearchExportManager
from .utils import (
    ErrorMessage,
    check_fields_limit,
    track_api_usage,
    update_user_data_last_accessed,
)

logger = get_nzdpu_logger()

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)


@router.post("", response_model=SearchResponse)
async def search(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    query: SearchQuery,
    view_id: int,
    start: int = 0,
    limit: int | None = None,
) -> SearchResponse:
    """
    Return the results of the selected query.

    Parameters
    ----------
        view_id (int): Table view ID of the submission to query.
        start (int): The pagination offset.
        limit (int): The query size limit.
        query (SearchQuery): The search query.

    Returns
    -------
        SearchResponse: The search results
    """
    check_fields_limit(query.fields)

    async with db_manager.get_session() as _session:
        # try:
        table_views = await static_cache.table_views()
        table_view = table_views.get(view_id)
        if not table_view:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE},
            )

        common_kwargs = {
            "session": _session,
            "redis_cache": cache,
            "cache": static_cache,
        }
        transformer = QueryDSLTransformer(
            table_view=table_view,
            query=query,
            offset=start,
            limit=limit,
            **common_kwargs,
        )

        finder = SubmissionFinder(transformer=transformer, **common_kwargs)

        results = await finder.load_all()

    page_size = min(limit, len(results)) if limit is not None else len(results)

    response = SearchResponse(
        start=start,
        size=page_size,
        total_disclosures=transformer.total_count,
        total_companies=transformer.total_companies,
        items=results,
    )
    return response


@router.post(
    "/download",
    response_model=None,  # This is done because FileResponse is not a pydantic model and we can't use Union to both FileResponse and DownloadExceedResponse
)
@track_api_usage(api_endpoint=TrackingUrls.SEARCH_DOWNLOAD.value)
async def download(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    query: SearchQuery,
    view_id: int,
    current_user: User = Depends(
        RoleAuthorizationForMultipleAuth(
            [
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ],
        )
    ),
) -> FileResponse | DownloadExceedResponse:
    """
    Return the results of the selected query.

    Parameters
    ----------
        view_id (int): Table view ID of the submission to query.
        query (SearchQuery): The search query.
    Returns
    -------
        FileResponse: Download to excel
    """
    check_fields_limit(query.fields)
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
    async with db_manager.get_session() as _session:
        table_views = await static_cache.table_views()
        table_view = table_views.get(view_id)
        if not table_view:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE},
            )
        common_kwargs = {
            "session": _session,
            "redis_cache": cache,
            "cache": static_cache,
        }
        transformer = QueryDSLTransformer(
            table_view=table_view,
            query=query,
            **common_kwargs,
        )

        finder = SubmissionFinder(
            transformer=transformer, export=True, **common_kwargs
        )
        results = await finder.load_all()
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "submission_result": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )

        # check if query.field is not empty to deside which download is
        down_all = len(query.fields) <= 1
        download_generator = SearchExportManager(
            cache=cache,
            session=_session,
            query_results=results,
            query=query,
            static_cache=static_cache,
        )
        filename = "nzdpu_data_explorer_table.xlsx"
        try:
            excel_filename = await download_generator.download_excel(
                filename=filename, down_all=down_all
            )
        except DownloadExceedMaximumException as exc:
            return DownloadExceedResponse(
                companies_count=exc.company_count,
                error_message=exc.message,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"submission_result": str(exc)},
            ) from exc

        return FileResponse(
            excel_filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )


# Disabled for now. Leaving it here for future reference.
# @router.post(
#     "/download-all",
#     response_model=None,  # This is done because FileResponse is not a pydantic model and we can't use Union to both FileResponse and DownloadExceedResponse
# )
# @track_api_usage(api_endpoint=TrackingUrls.SEARCH_DOWNLOAD_ALL.value)
# async def download_all(
#     db_manager: DbManager,
#     view_id: int,
#     static_cache: StaticCache,
#     current_user: User = Depends(
#         RoleAuthorizationForMultipleAuth(
#             [
#                 # removed the roles due to this issue: https://insomniacdesign.atlassian.net/browse/NZSOW4-141
#                 # AuthRole.DATA_EXPLORER,
#                 # AuthRole.DATA_PUBLISHER,
#                 # AuthRole.SCHEMA_EDITOR,
#                 AuthRole.ADMIN,
#             ],
#         )
#     ),
# ) -> FileResponse | DownloadExceedResponse:
#     """
#     Return the results of all forms and sub-forms.

#     Parameters
#     ----------
#         view_id (int): Table view ID of the submission to query.

#     Returns
#     -------
#         FileResponse: Download ALL to excel
#     """
#     _session: AsyncSession
#     async with db_manager.get_session() as _session:
#         # Update user.data_last_accessed for keeping track of inactivity
#         await update_user_data_last_accessed(
#             session=_session, current_user=current_user
#         )
#     async with db_manager.get_session() as _session:
#         table_view = await _session.get(TableView, view_id)
#         if not table_view:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail={"view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE},
#             )
#         table_def = await _session.get(TableDef, table_view.table_def_id)
#         if not table_def:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail={"view_id": ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE},
#             )
#         table_def_name = table_def.name
#         if not table_def_name:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail={"view_id": ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE},
#             )
#         # Create a storage client.
#         db_download_all_flag = await _session.scalar(
#             select(Config.value).where(
#                 Config.name == ConfigProperty.DATA_EXPLORER_DOWNLOAD_ALL
#             )
#         )
#         if db_download_all_flag is None:
#             raise HTTPException(
#                 status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#                 detail={
#                     "global": "No 'data_explorer_download_all' flag in config!"
#                 },
#             )

#         static_service = SearchService(db_manager, static_cache)
#         submission_count = await static_service.count_all_submissions()

#         if submission_count > MAXIMUM_DOWNLOAD_COMPANIES_EXCEL:
#             return DownloadExceedResponse(
#                 companies_count=submission_count,
#                 error_message=EXCEL_DOWNLOAD_TOO_MANY_COMPANIES,
#             )

#         download_all_flag = int(db_download_all_flag)
#         filename_prefix = "nzdpu_data"
#         filename_suffix = "all" if download_all_flag else "sample"
#         filename_extension = "zip"
#         filename = f"{filename_prefix}_{filename_suffix}.{filename_extension}"
#         logger.debug(f"Retrieving file {filename} from bucket")
#         storage_client = storage.Client()

#         bucket = storage_client.get_bucket(settings.gcp.default_bucket)

#         # name of the blob (file) in the bucket.
#         blob = bucket.blob(filename)

#         # download the blob to a file
#         zip_filename = filename
#         with open(zip_filename, "wb") as zip_obj:
#             try:
#                 blob.download_to_file(zip_obj)
#             except Exception as exc:
#                 raise HTTPException(
#                     status_code=404,
#                     detail={"storage": ErrorMessage.FILE_NOT_FOUND},
#                 ) from exc
#         return FileResponse(
#             zip_filename,
#             media_type="application/zip",
#             filename=zip_filename,
#         )


# Disabled for now. Leaving it here for future reference.
# @router.post(
#     "/download-selected",
#     response_model=None,  # This is done because FileResponse is not a pydantic model and we can't use Union to both FileResponse and DownloadExceedResponse
# )
# @track_api_usage(api_endpoint=TrackingUrls.SEARCH_DOWNLOAD_SELECTED.value)
# async def download_selected(
#     static_cache: StaticCache,
#     cache: Cache,
#     db_manager: DbManager,
#     query: SearchQuery,
#     view_id: int,
#     submission_ids: str,
#     current_user: User = Depends(
#         RoleAuthorizationForMultipleAuth(
#             [
#                 AuthRole.ADMIN,
#             ],
#         )
#     ),
# ) -> FileResponse | DownloadExceedResponse:
#     """
#     Return the results of the selected query.

#     Parameters
#     ----------
#         view_id (int): Table view ID of the submission to query.
#         query (SearchQuery): The search query.
#         submission_ids (string, required): list of submission identifiers
#          corresponding to the selected rows
#     Returns
#     -------
#         FileResponse: Download to excel
#     """
#     check_fields_limit(query.fields)
#     _session: AsyncSession
#     async with db_manager.get_session() as _session:
#         # Update user.data_last_accessed for keeping track of inactivity
#         await update_user_data_last_accessed(
#             session=_session, current_user=current_user
#         )
#     async with db_manager.get_session() as _session:
#         submission_ids_list = submission_ids.split(",")
#         try:
#             submission_ids_list = [int(x) for x in submission_ids_list]
#         except HTTPException as exc:
#             raise HTTPException(
#                 status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#                 detail="All elements in submission_ids must be integers",
#             ) from exc

#         table_views = await static_cache.table_views()
#         table_view = table_views.get(view_id)
#         if not table_view:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail={"view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE},
#             )
#         common_kwargs = {
#             "session": _session,
#             "redis_cache": cache,
#             "cache": static_cache,
#         }
#         transformer = QueryDSLTransformer(
#             submission_ids=submission_ids_list,
#             table_view=table_view,
#             query=query,
#             **common_kwargs,
#         )

#         finder = SubmissionFinder(
#             transformer=transformer, export=True, **common_kwargs
#         )
#         results = await finder.load_all()

#         # check if query.field is not empty to deside which download is
#         down_all = len(query.fields) <= 1
#         download_generator = SearchExportManager(
#             cache=cache,
#             session=_session,
#             query_results=results,
#             query=query,
#             static_cache=static_cache,
#         )
#         filename = "nzdpu_data_explorer_rows.xlsx"

#         try:
#             excel_filename = await download_generator.download_excel(
#                 filename=filename, down_all=down_all
#             )
#         except DownloadExceedMaximumException as exc:
#             return DownloadExceedResponse(
#                 companies_count=exc.company_count,
#                 error_message=exc.message,
#             )

#         return FileResponse(
#             excel_filename,
#             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#             filename=filename,
#         )
