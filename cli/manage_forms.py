"""CLI commands for building forms"""

import asyncio
import json
from time import perf_counter
from typing import Optional

import typer
from typing_extensions import Annotated

import app.settings as settings
from app.db.database import DBManager
from app.db.redis import RedisClient
from app.forms.form_builder import FormBuilder
from app.forms.form_reader import FormReader
from app.migration_tools import FormMigrationDataBuilder
from app.schemas.create_form import CreateForm
from app.schemas.get_form import GetForm
from app.schemas.table_view import FormGetFull
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder

# create CLI app
app = typer.Typer()


# ASYNC FUNCTIONS


async def async_create(path: str) -> None:
    """
    Asynchronous function to create forms.
    """
    # load form specification
    with open(path, encoding="utf-8") as f_spec:
        j_spec = json.load(f_spec)

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # validates and builds the schema
        form_spec = CreateForm(**j_spec)
        # builds the form
        builder = FormBuilder()
        await builder.go_build(spec=form_spec, session=session)


async def async_read(table_id: int) -> None:
    """
    Asynchronous function to read form definitions.
    """
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # read the form definition
        reader = FormReader(root_id=table_id)
        form_spec: Optional[GetForm | FormGetFull] = await reader.read(session)
        d_spec = form_spec.model_dump(exclude_none=True) if form_spec else {}
        print(json.dumps(d_spec, indent=4, default=str))


async def async_generate_submissions(
    n: int,
    table_view_id: int,
    tpl: str | None = None,
) -> None:
    """
    Generate submissions
    Parameters
    ----------
    n - number of submissions
    table_view_id - table view identifier
    tpl - Optional file name of template fle.
    """
    s = perf_counter()
    print("Generating submissions...")
    db_manager = DBManager()
    redis_cache = RedisClient(
        host=settings.cache.host,
        port=settings.cache.port,
        password=settings.cache.password,
    )

    async with db_manager.get_session() as session:
        static_cache = CoreMemoryCache(session)
        await static_cache.load_data()

        builder = SubmissionBuilder(
            session=session, cache=redis_cache, static_cache=static_cache
        )

        for i in range(n):
            print(f"Generating submission n {i + 1}...", end=" " * 30 + "\r")
            await builder.generate(table_view_id=table_view_id)
        print(f"Done in {perf_counter() - s}." + " " * 30)


# SYNC COMMANDS


@app.command()
def create(path: str) -> None:
    """
    Create a complete form model from a JSON specification

        Parameters:
        path - path to the form specification file
    """

    asyncio.run(async_create(path))


@app.command()
def read(table_id: int) -> None:
    """
    Return the complete definition of a form

    Parameters:
        table_id - identifier of the root table

    Returns:
        the complete form definition, in JSON format
    """

    asyncio.run(async_read(table_id))


# pylint: disable = invalid-name
@app.command()
def generate_submissions(
    n: int,
    table_view_id: int,
    tpl: Annotated[
        str,
        typer.Option(
            help=(
                "Specify the filename of a JSON file containing submission"
                " values to use it as a template"
            ),
        ),
    ] = "nzdpu-v40-sub.json",
) -> None:
    """
    Generates a predefined number of fake submissions in a table view.

    Args:
        n (int): the number of fake submissions to be generated.
    """

    asyncio.run(async_generate_submissions(n, table_view_id, tpl))


@app.command()
def generate_migration(path: str):
    # load form specification
    with open(path, encoding="utf-8") as f_spec:
        j_spec = json.load(f_spec)

    # validates and builds the schema
    form_spec = CreateForm(**j_spec)
    # save WIS data for form
    builder = FormMigrationDataBuilder()
    builder.build(spec=form_spec)
    builder.save()
    print("Done.")


if __name__ == "__main__":
    # start CLI App
    app()
