import asyncio
import json
import traceback
from os import listdir
from os.path import isdir, isfile, join
from typing import Optional

import httpx
import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DBManager
from app.db.models import SubmissionObj
from app.utils import reflect_form_table
from cli.helpers import get_access_token

app = typer.Typer()


def read_restatements_from_file(file_path: str) -> dict | None:
    with open(file_path, encoding="utf-8") as f_spec:
        try:
            j_spec = json.load(f_spec)
            return j_spec
        except json.JSONDecodeError:
            print(
                "ERROR: Invalid schema, json is not valid for file: ",
                file_path,
            )
            return None


async def get_submission_name(session: AsyncSession, nz_id: int) -> str | None:
    form_table = await reflect_form_table(session, "nzdpu_form")

    query = (
        select(SubmissionObj.name)
        .join(form_table, SubmissionObj.id == form_table.c.obj_id)
        .where(SubmissionObj.nz_id == nz_id)
        .order_by(
            form_table.c.reporting_year.desc(), SubmissionObj.revision.desc()
        )
    )

    result = await session.execute(query)
    result_items = list(result.scalars())

    if len(result_items) > 0:
        return result_items[0]
    else:
        print(f"ERROR: No submission found for company with id {nz_id}")
        return


async def handle_restatements_insertion(
    session: AsyncSession,
    restatement: dict,
    url: str,
    access_token: str,
    file: str,
):
    submission_name = await get_submission_name(
        session, restatement.get("nz_id")
    )
    if not submission_name:
        return
    result_checkout = httpx.post(
        url=f"{url}/submissions/revisions/{submission_name}/edit?force=false",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if result_checkout.status_code != 200:
        print(
            f"ERROR: problem with checking out the submission on file {file}: {result_checkout.json()}"
        )
        return

    result = httpx.post(
        url=f"{url}/submissions/revisions/{submission_name}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "reporting_datetime": restatement.get("reporting_datetime"),
            "data_source": restatement.get("data_source"),
            "restatements": restatement.get("restatements"),
        },
    )

    if result.status_code != 200:
        print(
            f"ERROR: problem with creating revision for submission on file {file}: {result.json()}"
        )
        return

    print(f"Successfully inserted restatements on file {file}")


async def ingest_restatements(
    path: str,
    username: str,
    password: str,
    url: str,
):
    access_token = get_access_token(url, username, password)
    if access_token:
        print("INFO: Successfully logged in.")
    else:
        print("ERROR: Invalid login credentials.")
        return

    if not isdir(path):
        print(f"ERROR: Path must be a folder: {path}")
        return
    only_files = [f for f in listdir(path) if isfile(join(path, f))]

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        for file in only_files:
            restatement_obj = read_restatements_from_file(join(path, file))
            if restatement_obj is None:
                continue

            await handle_restatements_insertion(
                session, restatement_obj, url, access_token, file
            )


@app.command()
def ingest_restatements_command(
    folder_path: str,
    username: str,
    password: str,
    url: Optional[str | None] = "http://localhost:8000",
):
    try:
        asyncio.run(ingest_restatements(folder_path, username, password, url))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    app()
