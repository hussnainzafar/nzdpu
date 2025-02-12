# import companies (to Organization table) from a CSV file;

import asyncio
import csv
import traceback
from datetime import datetime
from io import StringIO

import aiofiles
import typer

from app.db.database import DBManager
from app.db.models import Organization

app = typer.Typer()


async def import_organizations_from_csv(
    file_path: str,
) -> None:
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        async with aiofiles.open(
            file_path, mode="r", encoding="utf-8-sig"
        ) as file:
            content = await file.read()
            content = content.lstrip("\ufeff").replace("\r\n", "\n")
            csv_reader = csv.DictReader(StringIO(content))
            for row in csv_reader:
                try:
                    row["id"] = int(row["id"])
                    active = row.pop("active").lower() == "true"
                    created_on = datetime.fromisoformat(row.pop("created_on"))
                    last_updated_on = datetime.fromisoformat(
                        row.pop("last_updated_on")
                    )

                    company = Organization(
                        **row,
                        active=active,
                        created_on=created_on,
                        last_updated_on=last_updated_on,
                    )

                    session.add(company)
                    print(
                        f"INFO: Company {company.legal_name} added successfully."
                    )

                except KeyError as e:
                    print(f"ERROR: Missing expected field {e} in the CSV row.")

            await session.commit()


@app.command()
def import_organizations(file_path: str):
    try:
        asyncio.run(import_organizations_from_csv(file_path))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    app()
