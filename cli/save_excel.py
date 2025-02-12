"""Download all CLI."""

import asyncio
import os
import sys
import zipfile
from enum import Enum

import typer
from fastapi import HTTPException, status
from google.cloud import storage
from sqlalchemy.future import select

from app import settings
from app.db.database import DBManager
from app.db.models import Organization, TableDef, TableView
from app.db.redis import RedisClient
from app.loggers import get_nzdpu_logger
from app.routers.utils import ErrorMessage
from app.schemas.enums import SortOrderEnum
from app.schemas.search import (
    SearchDSLMetaElement,
    SearchDSLSortOptions,
    SearchQuery,
)
from app.search_dsl import SearchDSL
from app.service.core.cache import CoreMemoryCache
from app.service.core.errors import SubmissionError
from app.service.download_excel_cli_service import SaveExcelFileService
from app.service.exports.search_download import SearchExportManager

settings.setup_logging()
logger = get_nzdpu_logger()
# Import all other necessary modules and function

app = typer.Typer()


class SearchErrors(str, Enum):
    """
    Search DSL errors.
    """

    ATTRIBUTE_MULTIPLE_FORMS = (
        "The requested attribute was defined in multiple forms"
    )
    TABLE_FORM_NOT_FOUND = "Form is not found"


def make_filename(
    table_name: str,
    source: bool = False,
    last_updated: bool = False,
    sample: bool = False,
):
    """Generate a filename based on table name, source and last_updated flag."""
    filename_suffix = "sample" if sample else "all"
    filename_extension = "xlsx"
    flag_suffix = (
        "_last_updated"
        if source and last_updated
        else "_source"
        if source
        else ""
    )
    return f"{table_name}_data_{filename_suffix}{flag_suffix}.{filename_extension}"


def zip_files(filenames, output_filename):
    """Zip multiple files together."""
    with zipfile.ZipFile(output_filename, "w") as zf:
        for file in filenames:
            zf.write(file, arcname=os.path.basename(file))
    return output_filename


async def generate_excel(
    excel_generator: SearchExportManager,
    table_name: str,
    source: bool = False,
    last_updated: bool = False,
    sample: bool = False,
):
    """Download an Excel file and return its local path."""

    filename = make_filename(table_name, source, last_updated, sample)
    local_file_path = await excel_generator.download_excel(
        filename=filename,
        source=source,
        last_updated=last_updated,
        down_all=True,
    )
    logger.info(f"{local_file_path=}")
    return local_file_path


async def generate_excel_file(
    session,
    query,
    view_id,
    cache,
    table_name,
    sample=False,
    source=False,
    last_updated=False,
):
    static_cache = CoreMemoryCache(session)
    await static_cache.load_data()
    # construct sql script
    dsl = SearchDSL(
        static_cache=static_cache,
        session=session,
        query=query,
        view_id=view_id,
        cache=cache,
    )
    # execute and get results
    results = await dsl.get_results(export=True, down_all_restated=source)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "submission_result": SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
            },
        )
    logger.info(f"Got {len(results)} results. Generating Excel file...")
    # construct download generator
    excel_generator = SearchExportManager(
        static_cache=static_cache,
        cache=cache,
        session=session,
        query_results=results,
        query=query,
    )
    return await generate_excel(
        excel_generator=excel_generator,
        table_name=table_name,
        sample=sample,
        source=source,
        last_updated=last_updated,
    )


async def download(
    db_manager: DBManager, view_id: int, upload: bool, sample: bool = False
):
    """Download three Excel files, zip them and upload to GCP bucket."""

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(settings.gcp.default_bucket)

    query = SearchQuery(
        sort=[
            {"company_name": SearchDSLSortOptions(order=SortOrderEnum.ASC)},
            {"reporting_year": SearchDSLSortOptions(order=SortOrderEnum.DESC)},
        ],
        meta=SearchDSLMetaElement(),
    )
    async with db_manager.get_session() as session:
        table_view = await session.scalar(
            select(TableView).where(TableView.id == view_id)
        )
        if not table_view:
            logger.info(
                "An error occurred:", ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE
            )
            sys.exit(1)

        table_def = await session.scalar(
            select(TableDef).where(TableDef.id == table_view.id)
        )
        if not table_def:
            logger.info("view_id:", ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE)
            sys.exit(1)

        table_name = table_def.name
        # format table name without form string
        table_name = table_name.split("_")[0]
        # download regular Excel file
        cache = RedisClient(
            settings.cache.host, settings.cache.port, settings.cache.password
        )
        logger.info("Start generating all 3 files...")
        # Generate sample Excel file
        file1 = await generate_excel_file(
            session=session,
            query=query,
            view_id=view_id,
            cache=cache,
            table_name=table_name,
            sample=True,
        )
        # Generate data source sample Excel files
        file2 = await generate_excel_file(
            session=session,
            query=query,
            view_id=view_id,
            cache=cache,
            table_name=table_name,
            sample=True,
            source=True,
        )
        # Generate last updated sample Excel files
        file3 = await generate_excel_file(
            session=session,
            query=query,
            view_id=view_id,
            cache=cache,
            table_name=table_name,
            sample=True,
            source=True,
            last_updated=True,
        )
        if upload:
            # zip the two files together
            filename_suffix = "sample" if sample else "all"
            filename_extension = "zip"
            zip_name = (
                f"{table_name}_data_{filename_suffix}.{filename_extension}"
            )
            zip_path = zip_files([file1, file2, file3], zip_name)

            # Upload the zipped file to GCP
            blob = bucket.blob(zip_path)
            blob.upload_from_filename(zip_path)
            logger.info(
                f"{zip_path} uploaded to {settings.gcp.default_bucket}."
            )

            # clean up local files
            os.remove(zip_path)
            os.remove(file1)
            os.remove(file2)
            os.remove(file3)

        logger.info("Done")


@app.command()
def download_all(view_id: int, upload: bool = True, sample: bool = True):
    """
    Download all forms and sub-forms.

    Parameters
    ----------
        view_id (int): Table view ID of the submission to query.
    """
    session = DBManager()
    asyncio.run(download(session, view_id, upload, sample))


def save_excel_file_in_bucket(file_name):
    try:
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(settings.gcp.default_bucket)
        blob = bucket.blob(file_name)
        blob.upload_from_filename(file_name)
        logger.info(f"{file_name} uploaded to {settings.gcp.default_bucket}.")
        return blob.public_url
    except Exception as e:
        logger.error(f"ERROR: {e}")
    return None


async def save_excel_file_to_bucket(nz_id):
    _session = DBManager()
    async with _session.get_session() as session:
        static_cache = CoreMemoryCache(session)
        await static_cache.load_data()
        cache = RedisClient(
            settings.cache.host, settings.cache.port, settings.cache.password
        )
        save_excel = SaveExcelFileService(session, static_cache, cache)
        excel_filename_without_sics = (
            await save_excel.download_company_history_cli(
                nz_id=nz_id, exclude_classification_forced=True
            )
        )
        excel_filename_with_sics = (
            await save_excel.download_company_history_cli(
                nz_id=nz_id, exclude_classification_forced=False
            )
        )

        if settings.application.save_companies_files_to_bucket:
            for excel_filename in [
                excel_filename_without_sics,
                excel_filename_with_sics,
            ]:
                if excel_filename:
                    file_path = save_excel_file_in_bucket(excel_filename)
                    if file_path:
                        await cache.set(str(nz_id), file_path)
                        os.remove(excel_filename)
                    else:
                        logger.error(f"Failed to upload {excel_filename}.")
                else:
                    logger.info(
                        f"No companies or history found with nz_id: {nz_id}"
                    )


async def save_all_companies_to_bucket():
    _session = DBManager()
    async with _session.get_session() as session:
        result = await session.execute(select(Organization))
        payload = result.scalars().all()
        if payload:
            for org in payload:
                await save_excel_file_to_bucket(org.nz_id)
        else:
            logger.info("No Companies found")


@app.command()
def save_to_bucket(nz_id: int | None = None):
    if nz_id:
        asyncio.run(save_excel_file_to_bucket(nz_id=nz_id))
    else:
        asyncio.run(save_all_companies_to_bucket())


if __name__ == "__main__":
    app()
