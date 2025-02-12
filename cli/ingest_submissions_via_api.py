# create CLI app
import asyncio
import json
import traceback
from os import listdir
from os.path import isdir, isfile, join
from typing import Optional

import requests
import typer

from cli.helpers import get_access_token

app = typer.Typer()


async def handle_submission_insertion(
    submissions: list[dict],
    url: str,
    access_token: str,
    file: str,
):
    valid_leis = []
    for submission in submissions:
        lei = submission.get("legal_entity_identifier")

        result = await asyncio.to_thread(
            requests.post,
            url=f"{url}/submissions",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"table_view_id": 1, "values": submission},
        )

        data = result.json()

        if result.status_code != 200:
            print(
                f"ERROR: could not insert submission with lei {lei} on file {file} error: ",
                data,
            )
        else:
            valid_leis.append(lei)

    if len(valid_leis) > 0:
        print(
            f"INFO: Uploaded submissions successfully from {file} with following LEIs: ",
            ", ".join(valid_leis),
        )


def read_submissions_from_file(file_path: str) -> list[dict] | None:
    submissions = []
    with open(file_path, encoding="utf-8") as f_spec:
        try:
            j_spec = json.load(f_spec)
            for key in list(j_spec.keys()):
                submission = j_spec.get(key)
                if isinstance(submission, dict):
                    submissions.append(submission)
                else:
                    print(
                        "WARNING: Submission is not formatted correctly, it is not a dict:",
                        submission,
                    )
            return submissions
        except json.JSONDecodeError:
            print(
                "ERROR: Invalid schema, json is not valid for file: ",
                file_path,
            )
            return None


async def ingest_submissions_async(
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
    for file in only_files:
        submissions = read_submissions_from_file(join(path, file))
        if submissions is None:
            continue

        await handle_submission_insertion(submissions, url, access_token, file)


@app.command()
def ingest_submissions(
    folder_path: str,
    username: str,
    password: str,
    url: Optional[str | None] = "http://localhost:8000",
):
    try:
        asyncio.run(
            ingest_submissions_async(folder_path, username, password, url)
        )
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    app()
